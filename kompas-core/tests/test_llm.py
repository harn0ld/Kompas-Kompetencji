import json
import socket
from datetime import datetime

import pytest

from kompas_core.llm import (
    BrakOdpowiedzi,
    Cytat,
    DziennikJsonl,
    DziennikPamiec,
    Ekstrakcyjny,
    Odpowiedz,
    Ollama,
    OpenAiZgodny,
    Tryb,
    Zapisane,
    Zapytanie,
    sprawdz_odpowiedz,
    wywolaj,
    z_konfiguracji,
)
from kompas_core.llm import dostawca as modul
from kompas_core.zrodla import Fragment

FRAGMENTY = [
    Fragment(id="rozp#1", doc_id="rozp", lokalizator="§ 11 ust. 1",
             tekst="Ocena jest negatywna, gdy jedno kryterium ma 1 punkt."),
    Fragment(id="rozp#2", doc_id="rozp", lokalizator="§ 7",
             tekst="Kryteria ustala się w terminie 30 dni od dnia zapoznania\nz oceną."),
    Fragment(id="ustawa#1", doc_id="ustawa", lokalizator="art. 83",
             tekst="Odwołanie wnosi się w terminie 7 dni od dnia zapoznania z oceną."),
]
ZEGAR = lambda: datetime(2026, 11, 21, 12, 0)  # noqa: E731


def zapytanie(pytanie="kiedy ocena jest negatywna?", katalog=()):
    return Zapytanie(operacja="asystent", prompt_wersja="p1", pytanie=pytanie,
                     fragmenty=FRAGMENTY, katalog=list(katalog))


class Atrapa:
    nazwa, model, tryb = "atrapa", "zmyslacz-1", Tryb.NA_ZYWO

    def __init__(self, odpowiedz=None, wyjatek=None):
        self._o, self._e = odpowiedz, wyjatek

    def odpowiedz(self, z):
        if self._e:
            raise self._e
        return self._o


def test_zmyslony_cytat_odrzucony_fallback_i_log():
    zmyslacz = Atrapa(Odpowiedz(cytaty=[Cytat(fragment_id="rozp#1",
                                              cytat="Ocena jest negatywna, gdy średnia jest niska.")]))
    log = DziennikPamiec()
    wynik = wywolaj(zapytanie(), [zmyslacz, Ekstrakcyjny()], log, ZEGAR)

    assert wynik.dostawca == "ekstrakcyjny" and wynik.tryb is Tryb.EKSTRAKCYJNE
    assert wynik.odrzuceni == ["atrapa"]
    assert wynik.odpowiedz.cytaty[0].fragment_id == "rozp#1"
    odrzucony, przyjety = log.wpisy
    assert not odrzucony.walidacja_ok and "bez pokrycia" in odrzucony.bledy[0]
    assert odrzucony.model == "zmyslacz-1" and odrzucony.prompt_wersja == "p1"
    assert odrzucony.fragment_ids == ["rozp#1", "rozp#2", "ustawa#1"]
    assert odrzucony.tryb is Tryb.NA_ZYWO and odrzucony.czas == ZEGAR()
    assert przyjety.walidacja_ok and przyjety.tryb is Tryb.EKSTRAKCYJNE


def test_poprawna_odpowiedz_na_zywo_z_lamaniem_wiersza_jest_przyjeta():
    dobra = Atrapa(Odpowiedz(
        cytaty=[Cytat(fragment_id="rozp#2", cytat="od dnia zapoznania z oceną")],
        wybor=["k7"], tresc="30 dni",
    ))
    wynik = wywolaj(zapytanie(katalog=["k7"]), [dobra, Ekstrakcyjny()], DziennikPamiec(), ZEGAR)
    assert wynik.dostawca == "atrapa" and wynik.odrzuceni == []


@pytest.mark.parametrize("odp, blad", [
    (Odpowiedz(cytaty=[Cytat(fragment_id="obcy#9", cytat="x")]), "nie był w zapytaniu"),
    (Odpowiedz(cytaty=[Cytat(fragment_id="rozp#1", cytat="Ocena jest negatywna")], wybor=["k99"]),
     "spoza katalogu"),
    (Odpowiedz(cytaty=[]), "brak cytatów"),
    # Helix G3 (3): prawdziwy cytat, zmyślona liczba w treści.
    (Odpowiedz(cytaty=[Cytat(fragment_id="ustawa#1", cytat="Odwołanie wnosi się w terminie 7 dni")],
               tresc="Termin na sprzeciw wynosi 99 dni."), "liczby w treści bez pokrycia"),
])
def test_sprawdz_odpowiedz(odp, blad):
    assert any(blad in b for b in sprawdz_odpowiedz(zapytanie(katalog=["k1"]), odp))


def test_wyjatek_dostawcy_to_fallback():
    log = DziennikPamiec()
    wynik = wywolaj(zapytanie(), [Atrapa(wyjatek=ConnectionError("brak sieci")), Ekstrakcyjny()], log)
    assert wynik.dostawca == "ekstrakcyjny"
    assert "ConnectionError" in log.wpisy[0].bledy[0]


def test_tryb_ekstrakcyjny_dziala_bez_sieci_i_klucza(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def bez_sieci(*a, **k):
        raise AssertionError("tryb ekstrakcyjny nie może używać sieci")

    monkeypatch.setattr(socket, "socket", bez_sieci)
    wynik = wywolaj(zapytanie("odwołanie termin"), [Ekstrakcyjny(k=1)], DziennikPamiec())
    assert wynik.odpowiedz.cytaty[0].fragment_id == "ustawa#1"
    assert wynik.odpowiedz.tresc.startswith("Odwołanie")


def test_brak_odpowiedzi_gdy_nic_nie_pasuje():
    with pytest.raises(BrakOdpowiedzi) as e:
        wywolaj(zapytanie("xyzzy"), [Ekstrakcyjny()], DziennikPamiec())
    assert e.value.wpisy[0].dostawca == "ekstrakcyjny"


def test_zapisane_odpowiedzi(tmp_path):
    plik = tmp_path / "demo.json"
    z = zapytanie()
    Zapisane.dopisz(plik, z, Odpowiedz(cytaty=[Cytat(fragment_id="rozp#1", cytat="Ocena jest negatywna")]))
    wynik = wywolaj(z, [Zapisane(plik)], DziennikPamiec())
    assert wynik.tryb is Tryb.ZAPISANE
    with pytest.raises(KeyError):
        Zapisane(plik).odpowiedz(zapytanie("inne pytanie"))


def test_dziennik_jsonl(tmp_path):
    plik = tmp_path / "log" / "llm.jsonl"
    wywolaj(zapytanie(), [Ekstrakcyjny()], DziennikJsonl(plik))
    wpis = json.loads(plik.read_text(encoding="utf-8").splitlines()[0])
    assert wpis["dostawca"] == "ekstrakcyjny" and wpis["walidacja_ok"] is True


def test_ollama_parsuje_json_z_odpowiedzi(monkeypatch):
    def post(url, dane, naglowki, timeout):
        assert url == "http://localhost:11434/api/chat" and dane["model"] == "llama3.1"
        assert "[rozp#1]" in dane["messages"][1]["content"]
        return {"message": {"content": 'Oto: {"cytaty": [{"fragment_id": "rozp#1", '
                                       '"cytat": "jedno kryterium ma 1 punkt"}], "tresc": null}'}}

    monkeypatch.setattr(modul, "_post_json", post)
    wynik = wywolaj(zapytanie(), [Ollama("llama3.1")], DziennikPamiec())
    assert wynik.dostawca == "ollama" and wynik.tryb is Tryb.NA_ZYWO


def test_openai_zgodny_wysyla_chat_completions_i_parsuje_odpowiedz(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sekret")

    def post(url, dane, naglowki, timeout):
        assert url == "https://api.example.test/v1/chat/completions"
        assert dane["model"] == "model-1" and dane["temperature"] == 0.2
        assert dane["response_format"] == {"type": "json_object"}
        assert naglowki == {"authorization": "Bearer sekret"} and timeout == 12
        assert "[rozp#1]" in dane["messages"][1]["content"]
        return {"choices": [{"message": {"content": json.dumps({
            "cytaty": [{"fragment_id": "rozp#1", "cytat": "jedno kryterium ma 1 punkt"}],
            "wybor": [],
            "tresc": "Ocena jest negatywna.",
        })}}]}

    monkeypatch.setattr(modul, "_post_json", post)
    dostawca = OpenAiZgodny(
        "https://api.example.test/v1/", "model-1", "DEEPSEEK_API_KEY", 12, 0.2
    )
    wynik = wywolaj(zapytanie(), [dostawca], DziennikPamiec())
    assert wynik.dostawca == "openai_zgodny" and wynik.tryb is Tryb.NA_ZYWO


def test_openai_zgodny_adres_ze_zmiennej_nadpisuje_konfiguracje(monkeypatch):
    """Klucz Scaleway ograniczony do projektu wymaga adresu z identyfikatorem projektu (ustawianego na serwerze)."""
    monkeypatch.setenv("KLUCZ_TESTOWY", "sekret")
    adresy = []

    def post(url, dane, naglowki, timeout):
        adresy.append(url)
        return {"choices": [{"message": {"content": json.dumps({
            "cytaty": [{"fragment_id": "rozp#1", "cytat": "jedno kryterium ma 1 punkt"}], "wybor": [], "tresc": "",
        })}}]}

    monkeypatch.setattr(modul, "_post_json", post)
    dostawca = OpenAiZgodny("https://api.example.test/v1", "model-1", "KLUCZ_TESTOWY", zmienna_adresu="ADRES_TESTOWY")
    monkeypatch.delenv("ADRES_TESTOWY", raising=False)
    wywolaj(zapytanie(), [dostawca], DziennikPamiec())
    monkeypatch.setenv("ADRES_TESTOWY", "https://api.example.test/projekt-1/v1/")
    wywolaj(zapytanie(), [dostawca], DziennikPamiec())
    assert adresy == [
        "https://api.example.test/v1/chat/completions",
        "https://api.example.test/projekt-1/v1/chat/completions",
    ]


def test_openai_zgodny_bez_klucza_przechodzi_do_fallbacku(monkeypatch):
    monkeypatch.delenv("NIE_MA_TAKIEGO_KLUCZA", raising=False)
    dostawca = OpenAiZgodny("https://api.example.test", "model-1", "NIE_MA_TAKIEGO_KLUCZA")
    log = DziennikPamiec()
    wynik = wywolaj(zapytanie(), [dostawca, Ekstrakcyjny()], log)
    assert wynik.dostawca == "ekstrakcyjny"
    assert "brak NIE_MA_TAKIEGO_KLUCZA" in log.wpisy[0].bledy[0]


@pytest.mark.parametrize("odpowiedz", [
    {"choices": [{"message": {"content": "to nie jest JSON"}}]},
    {"choices": [{"message": {"content": json.dumps({
        "cytaty": [{"fragment_id": "rozp#1", "cytat": "zmyślony cytat"}]
    })}}]},
])
def test_openai_zgodny_bledna_odpowiedz_przechodzi_do_fallbacku(
    monkeypatch, odpowiedz
):
    monkeypatch.setenv("API_KEY", "sekret")
    monkeypatch.setattr(modul, "_post_json", lambda *args, **kwargs: odpowiedz)
    dostawca = OpenAiZgodny("https://api.example.test", "model-1", "API_KEY")
    wynik = wywolaj(zapytanie(), [dostawca, Ekstrakcyjny()], DziennikPamiec())
    assert wynik.dostawca == "ekstrakcyjny"


def test_openai_zgodny_blad_http_przechodzi_do_fallbacku(monkeypatch):
    monkeypatch.setenv("API_KEY", "sekret")

    def blad(*args, **kwargs):
        raise ConnectionError("HTTP 503")

    monkeypatch.setattr(modul, "_post_json", blad)
    dostawca = OpenAiZgodny("https://api.example.test", "model-1", "API_KEY")
    wynik = wywolaj(zapytanie(), [dostawca, Ekstrakcyjny()], DziennikPamiec())
    assert wynik.dostawca == "ekstrakcyjny"


def test_openai_zgodny_z_konfiguracji():
    dostawcy = z_konfiguracji({"dostawcy": [{
        "typ": "openai_zgodny",
        "base_url": "https://api.example.test/v1",
        "model": "model-1",
        "zmienna_klucza": "API_KEY",
        "timeout": 9,
        "temperatura": 0.1,
    }]})
    dostawca = dostawcy[0]
    assert isinstance(dostawca, OpenAiZgodny)
    assert dostawca.timeout == 9 and dostawca.temperatura == 0.1


def test_dostawca_z_konfiguracji_wersji(tmp_path):
    v1 = z_konfiguracji({"dostawcy": [{"typ": "anthropic", "model": "m"}, {"typ": "ekstrakcyjny"}]})
    assert [d.nazwa for d in v1] == ["anthropic", "ekstrakcyjny"]
    mc = {"dozwolone": ["ollama", "zapisane", "ekstrakcyjny"],
          "dostawcy": [{"typ": "ollama", "model": "llama3.1"}, {"typ": "ekstrakcyjny"}]}
    assert [d.nazwa for d in z_konfiguracji(mc)] == ["ollama", "ekstrakcyjny"]
    mc["dostawcy"].insert(0, {"typ": "anthropic", "model": "m"})
    with pytest.raises(ValueError, match="niedozwolony"):
        z_konfiguracji(mc)
    with pytest.raises(ValueError, match="nieznany"):
        z_konfiguracji({"dostawcy": [{"typ": "gpt"}]})


class DziennikNiezapisywalny:
    def zapisz(self, wpis):
        raise OSError("brak miejsca na dysku")


def test_blad_zapisu_dziennika_nie_przerywa_odpowiedzi(caplog):
    wynik = wywolaj(zapytanie(), [Ekstrakcyjny()], DziennikNiezapisywalny(), ZEGAR)
    assert wynik.dostawca == "ekstrakcyjny" and wynik.odpowiedz.cytaty
    assert "nie zapisano wpisu dziennika" in caplog.text


def test_liczba_z_pytania_nie_legalizuje_odpowiedzi():
    """Helix G3 runda 2: pytanie z „99 dni” nie czyni tej liczby dozwoloną w odpowiedzi."""
    odp = Odpowiedz(cytaty=[Cytat(fragment_id="ustawa#1", cytat="Odwołanie wnosi się w terminie 7 dni")],
                    tresc="Termin na sprzeciw wynosi 99 dni.")
    bledy = sprawdz_odpowiedz(zapytanie(pytanie="Czy zgodnie z art. 83 termin wynosi 99 dni?"), odp)
    assert any("liczby w treści bez pokrycia" in b for b in bledy)


def test_liczby_z_fragmentu_i_numery_listy_przechodza():
    """Liczby z cytowanego fragmentu i z pytania są dozwolone; numer punktu listy nie jest twierdzeniem."""
    odp = Odpowiedz(cytaty=[Cytat(fragment_id="ustawa#1", cytat="Odwołanie wnosi się w terminie 7 dni")],
                    tresc="1. Odwołanie wnosi się w ciągu 7 dni.\n2. Liczy się od zapoznania z oceną (art. 83).")
    assert sprawdz_odpowiedz(zapytanie(pytanie="art. 83 odwołanie"), odp) == []


def test_tresc_jako_obiekt_json_jest_zapisana_jako_tekst():
    """#176: DeepSeek przez Scaleway często zwraca „tresc” jako obiekt zamiast tekstu z JSON-em; odpowiedź
    nie może przez to odpaść (opis osoby z modelem padał w 3 z 4 prób)."""
    o = Odpowiedz.model_validate({"cytaty": [], "tresc": {"zdania": [{"tekst": "Zdanie.", "fakty": ["k1"]}]}})
    assert json.loads(o.tresc) == {"zdania": [{"tekst": "Zdanie.", "fakty": ["k1"]}]}
    assert Odpowiedz.model_validate({"cytaty": [], "tresc": "zwykły tekst"}).tresc == "zwykły tekst"
