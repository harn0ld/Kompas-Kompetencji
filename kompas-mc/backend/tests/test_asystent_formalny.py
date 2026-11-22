"""Asystent formalny w pełnym zakresie (#37, M-11) na zestawach z konfiguracja/.

    cd kompas-mc/backend && uv run pytest tests/test_asystent_formalny.py -s

pytania-kontrolne.yaml – kryteria #37 (≥15 z bazy, ≥5 spoza bazy); progi dobrane na nim.
pytania-parafrazy.yaml – zestaw TESTOWY napisany przed FAQ; tylko pomiar, nie do strojenia.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from kompas_core.llm import DziennikJsonl, DziennikPamiec, Ekstrakcyjny, OpenAiZgodny, Ollama
from kompas_core.llm import dostawca as modul_dostawcy

from kompas_mc.asystent import Asystent, KonfiguracjaAsystenta
from kompas_mc.ustawienia import KATALOG_MC

KONF = KATALOG_MC / "konfiguracja"
KONTROLNE = yaml.safe_load((KONF / "pytania-kontrolne.yaml").read_text(encoding="utf-8"))
PARAFRAZY = yaml.safe_load((KONF / "pytania-parafrazy.yaml").read_text(encoding="utf-8"))
FAQ = yaml.safe_load((KONF / "faq.yaml").read_text(encoding="utf-8"))["pozycje"]
Z_BAZY, SPOZA = KONTROLNE["z_bazy"], KONTROLNE["spoza_bazy"]
WZORY = {q["id"]: q for q in Z_BAZY}

MIN_TRAFIEN = 15  # kryterium #37
# Wynik parafraz przy wprowadzeniu FAQ (15/22). Test pilnuje, żeby zmiany go nie obniżyły;
# nie podnosić progu przez dopisywanie sformułowań z parafraz do FAQ lub słownika.
MIN_PARAFRAZ = 15


def _sciezka(s: str) -> str | None:
    return None if s == "wspolne" else s


def _n(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"-\s*\n\s*", "", s)).strip()


@pytest.fixture(scope="module")
def asystent(korpus_mc, ustawienia, tmp_path_factory) -> Asystent:
    return Asystent(
        korpus_mc,
        KonfiguracjaAsystenta.z_pliku(ustawienia.konfiguracja_asystenta),
        DziennikJsonl(tmp_path_factory.mktemp("log") / "llm.jsonl"),
        dostawcy=[Ekstrakcyjny(k=3)],
    )


def _trafione(asystent: Asystent, pytanie: str, sciezka: str, ref: dict) -> bool:
    odp = asystent.odpowiedz(pytanie, _sciezka(sciezka))
    return odp.znaleziono and any(
        c.doc_id == ref["doc_id"] and _n(ref["cytat_dosłowny"]) in _n(c.cytat) for c in odp.cytaty
    )


# --- kryteria #37 --------------------------------------------------------------------


def test_zestaw_ma_wymagana_liczebnosc():
    assert len(Z_BAZY) >= 15 and len(SPOZA) >= 5


def test_co_najmniej_15_pytan_kontrolnych_przechodzi(asystent):
    chybione = [
        q["id"] for q in Z_BAZY
        if not _trafione(asystent, q["pytanie"], q["sciezka"], q["adnotacje"][0])
    ]
    print(f"\nkontrolne: {len(Z_BAZY) - len(chybione)}/{len(Z_BAZY)}; chybione: {chybione}")
    assert len(Z_BAZY) - len(chybione) >= MIN_TRAFIEN


@pytest.mark.parametrize("q", SPOZA, ids=[q["id"] for q in SPOZA])
def test_pytanie_spoza_bazy_daje_brak_informacji(asystent, q):
    odp = asystent.odpowiedz(q["pytanie"])
    assert odp.znaleziono is False and odp.cytaty == []
    assert odp.komunikat == "brak wystarczających informacji w bazie wiedzy"


@pytest.mark.parametrize("q", Z_BAZY, ids=[q["id"] for q in Z_BAZY])
def test_pytanie_z_bazy_nie_jest_odrzucane(asystent, q):
    assert asystent.odpowiedz(q["pytanie"], _sciezka(q["sciezka"])).znaleziono


@pytest.mark.parametrize("sciezka,obcy", [("pierwsza", "okresow"), ("okresowa", "pierwsz")])
def test_sciezki_nie_mieszaja_zrodel(asystent, korpus_mc, sciezka, obcy):
    obce = {d for d in korpus_mc.dokumenty if d not in korpus_mc.doc_ids_dla(sciezka)}
    assert any(obcy in d for d in obce)
    for q in Z_BAZY:
        if q["sciezka"] == sciezka:
            odp = asystent.odpowiedz(q["pytanie"], sciezka)
            assert not [c.doc_id for c in odp.cytaty if c.doc_id in obce], q["id"]


def test_ta_sama_tresc_inna_sciezka_inne_rozporzadzenie(asystent):
    pytanie = "Jaka jest skala punktowa ocen cząstkowych?"
    p = asystent.odpowiedz(pytanie, "pierwsza")
    o = asystent.odpowiedz(pytanie, "okresowa")
    assert p.cytaty[0].doc_id == "rozp-2015-pierwsza" and "7 pkt" in p.tresc
    assert o.cytaty[0].doc_id == "rozp-2016-okresowe" and "9" in o.tresc


def test_odpowiedz_z_poradnika_cytujacego_ustawe_jest_oznaczona(asystent):
    odp = asystent.odpowiedz("Pracownik nie zgadza się z oceną. Ile ma dni na sprzeciw?", "okresowa")
    assert odp.znaleziono and odp.cytaty[0].powoluje_ustawe
    assert odp.cytaty[0].kategoria.value == "OBJAŚNIENIE_MATERIAŁU"
    assert any("ustaw" in u for u in odp.uwagi)


def test_przepis_nie_jest_oznaczany(asystent):
    odp = asystent.odpowiedz("Ile kryteriów dodatkowych mogę wybrać?", "okresowa")
    assert all(not c.powoluje_ustawe for c in odp.cytaty if c.kategoria.value == "PRZEPIS")


def test_domyslny_lancuch_deepseek_ollama_ekstrakcyjny(ustawienia):
    plik = KONF / "asystent.yaml"
    llm = yaml.safe_load(plik.read_text(encoding="utf-8"))["llm"]
    assert "dozwolone" not in llm
    assert [d["typ"] for d in llm["dostawcy"]] == [
        "openai_zgodny", "ollama", "ekstrakcyjny"
    ]
    assert llm["dostawcy"][0] == {
        "typ": "openai_zgodny",
        "base_url": "https://api.scaleway.ai/v1",
        "model": "deepseek-v4-flash-0731",
        "zmienna_klucza": "SCALEWAY_API_KEY",
        "zmienna_adresu": "SCALEWAY_BASE_URL",
        "timeout": 30,
        "temperatura": 0.0,
    }
    konf = KonfiguracjaAsystenta.z_pliku(plik)
    # Typy wynikają z tej samej fabryki używanej przy starcie aplikacji.
    from kompas_core.llm import z_konfiguracji
    lancuch = z_konfiguracji(konf.llm)
    assert isinstance(lancuch[0], OpenAiZgodny)
    assert isinstance(lancuch[1], Ollama)
    assert isinstance(lancuch[2], Ekstrakcyjny)


def test_bez_klucza_i_ollamy_odpowiada_ekstrakcyjnie(
    korpus_mc, ustawienia, tmp_path, monkeypatch
):
    monkeypatch.delenv("SCALEWAY_API_KEY", raising=False)

    def brak_ollamy(*args, **kwargs):
        raise ConnectionError("Ollama niedostępna")

    monkeypatch.setattr(modul_dostawcy, "_post_json", brak_ollamy)
    asystent = Asystent(
        korpus_mc,
        KonfiguracjaAsystenta.z_pliku(KONF / "asystent.yaml"),
        DziennikJsonl(tmp_path / "llm.jsonl"),
    )
    odp = asystent.odpowiedz("Kiedy przeprowadza się rozmowę wstępną?", "pierwsza")
    assert odp.znaleziono and odp.tryb.value == "EKSTRAKCYJNE"
    assert odp.dostawca == "ekstrakcyjny"


def test_z_kluczem_poprawna_odpowiedz_deepseek_ma_tryb_na_zywo(
    korpus_mc, ustawienia, tmp_path, monkeypatch
):
    monkeypatch.setenv("SCALEWAY_API_KEY", "testowy-klucz")

    def odpowiedz_deepseek(url, dane, naglowki, timeout):
        assert url == "https://api.scaleway.ai/v1/chat/completions"
        assert dane["model"] == "deepseek-v4-flash-0731"
        assert naglowki["authorization"] == "Bearer testowy-klucz"
        tresc = dane["messages"][1]["content"]
        dopasowanie = re.search(r"\[([^]]+)]\n(.+?)(?:\n\n\[|\n\nPYTANIE:)", tresc, re.DOTALL)
        assert dopasowanie
        fragment_id, fragment = dopasowanie.groups()
        cytat = fragment
        return {"choices": [{"message": {"content": __import__("json").dumps({
            "cytaty": [{"fragment_id": fragment_id, "cytat": cytat}],
            "wybor": [],
            "tresc": cytat,
        })}}]}

    monkeypatch.setattr(modul_dostawcy, "_post_json", odpowiedz_deepseek)
    asystent = Asystent(
        korpus_mc,
        KonfiguracjaAsystenta.z_pliku(KONF / "asystent.yaml"),
        DziennikJsonl(tmp_path / "llm.jsonl"),
    )
    odp = asystent.odpowiedz("Kiedy przeprowadza się rozmowę wstępną?", "pierwsza")
    assert odp.znaleziono and odp.tryb.value == "NA_ŻYWO"
    assert odp.dostawca == "openai_zgodny"


def test_zmyslona_liczba_w_tresci_modelu_nie_przechodzi(korpus_mc, ustawienia, tmp_path, monkeypatch):
    """Helix G3 (3): prawdziwy cytat, ale treść z liczbą spoza fragmentów → odrzucenie i tryb bez modelu."""
    monkeypatch.setenv("SCALEWAY_API_KEY", "testowy-klucz")

    def zmyslacz(url, dane, naglowki, timeout):
        tresc = dane["messages"][1]["content"]
        fragment_id, fragment = re.search(r"\[([^]]+)]\n(.+?)(?:\n\n\[|\n\nPYTANIE:)", tresc, re.DOTALL).groups()
        return {"choices": [{"message": {"content": __import__("json").dumps({
            "cytaty": [{"fragment_id": fragment_id, "cytat": fragment}], "wybor": [],
            "tresc": "Termin na sprzeciw wynosi 99 dni.",
        })}}]}

    monkeypatch.setattr(modul_dostawcy, "_post_json", zmyslacz)
    asystent = Asystent(
        korpus_mc, KonfiguracjaAsystenta.z_pliku(KONF / "asystent.yaml"), DziennikJsonl(tmp_path / "llm.jsonl"),
    )
    odp = asystent.odpowiedz("Ile dni ma pracownik na sprzeciw od oceny okresowej?", "okresowa")
    assert "99" not in (odp.tresc or "")
    assert odp.dostawca != "openai_zgodny"


# --- jakość odpowiedzi -----------------------------------------------------------------


def test_cytaty_sa_doslowne_z_korpusu(asystent, korpus_mc):
    for q in Z_BAZY:
        for c in asystent.odpowiedz(q["pytanie"], _sciezka(q["sciezka"])).cytaty:
            assert c.cytat in korpus_mc.korpus.fragment(c.fragment_id).tekst
            assert c.wyrozniony and c.wyrozniony in c.cytat


@pytest.mark.parametrize(
    "pytanie,sciezka,fraza",
    [
        ("Kiedy przeprowadza się rozmowę wstępną?", "pierwsza", "21 dni"),
        ("Ile dni ma pracownik na sprzeciw?", "okresowa", "7 dni"),
        ("Ile kryteriów dodatkowych mogę wybrać?", "okresowa", "3"),
        ("Kiedy ocena okresowa jest negatywna?", "okresowa", "znacznie poniżej"),
    ],
)
def test_tresc_odpowiada_na_pytanie(asystent, pytanie, sciezka, fraza):
    assert fraza in asystent.odpowiedz(pytanie, sciezka).tresc


def test_nieznane_pojecie_jest_nazwane(asystent):
    odp = asystent.odpowiedz("Pracownik zgłasza mobbing. Co robić?")
    assert odp.znaleziono is False and "mobbing" in odp.nieznane_pojecia
    assert any("mobbing" in u for u in odp.uwagi)


def test_pytanie_o_artykul_ustawy_daje_ten_artykul(asystent):
    odp = asystent.odpowiedz("Co mówi art. 81 ustawy o służbie cywilnej?", "okresowa")
    assert odp.znaleziono and odp.faq_id is None and odp.cytaty
    assert all(c.doc_id == "ustawa-sc" and c.lokalizator.startswith("art. 81 ") for c in odp.cytaty)
    assert odp.cytaty[0].lokalizator == "art. 81 ust. 1" and odp.cytaty[0].kategoria.value == "PRZEPIS"
    assert all(c.wyrozniony == c.cytat.strip() for c in odp.cytaty)


def test_wskazany_ustep_u_s_c_bez_dopelniania_rankingiem(asystent):
    odp = asystent.odpowiedz("Co mówi art. 83 ust. 1 u.s.c.?")
    assert [(c.doc_id, c.lokalizator) for c in odp.cytaty] == [("ustawa-sc", "art. 83 ust. 1")]


def test_sprzeciw_cytuje_art_83_ustawy(asystent):
    odp = asystent.odpowiedz("Kiedy przysługuje sprzeciw od oceny okresowej?", "okresowa")
    art83 = [c for c in odp.cytaty if c.doc_id == "ustawa-sc" and c.lokalizator == "art. 83 ust. 1"]
    assert odp.znaleziono and art83 and "7 dni" in art83[0].cytat


def test_bez_ustawy_w_korpusie_pytanie_o_ustawe_daje_brak_ustawy(korpus_mc, ustawienia):
    konf = replace(KonfiguracjaAsystenta.z_pliku(ustawienia.konfiguracja_asystenta), ustawa="nie-ma")
    bez = Asystent(korpus_mc, konf, DziennikPamiec(), dostawcy=[Ekstrakcyjny(k=3)])
    for pytanie in ("Co mówi art. 81 ustawy o służbie cywilnej?", "Jaki termin sprzeciwu podaje u.s.c.?"):
        odp = bez.odpowiedz(pytanie, "okresowa")
        assert odp.znaleziono is False and odp.cytaty == []
        assert odp.uwagi == [konf.komunikaty["brak_ustawy"]]


def test_slowo_ustawic_nie_jest_pytaniem_o_ustawe(asystent):
    assert not asystent._pytanie_o_ustawe.search("Jak ustawić termin rozmowy?")
    odp = asystent.odpowiedz("Kiedy przeprowadza się rozmowę wstępną?", "pierwsza")
    assert odp.znaleziono and odp.cytaty[0].lokalizator == "§ 3"
    assert odp.cytaty[0].doc_id == "rozp-2015-pierwsza"


def test_slabe_pokrycie_pytania_poza_faq_daje_brak(asystent):
    # Słowa są w korpusie („na wypadek braku porozumienia”), więc tylko pokrycie to łapie.
    odp = asystent.odpowiedz("Jak zgłosić wypadek przy pracy?")
    assert odp.znaleziono is False and odp.cytaty == [] and odp.nieznane_pojecia == []


# --- przygotowany zestaw pytań i odpowiedzi ---------------------------------------------


def test_faq_nie_kopiuje_pytan_testowych():
    warianty = {_n(w).lower() for p in FAQ for w in p["pytania"]}
    testowe = {
        _n(q["pytanie"]).lower()
        for q in Z_BAZY + SPOZA + PARAFRAZY["z_bazy"] + PARAFRAZY["spoza_bazy"]
    }
    assert not warianty & testowe


def test_odpowiedz_z_faq_ma_cytat_zrodla(asystent):
    odp = asystent.odpowiedz("Do kiedy rozmowa wstępna z nowo przyjętym?", "pierwsza")
    assert odp.faq_id == "FAQ-P01" and odp.tryb.value == "EKSTRAKCYJNE"
    c = odp.cytaty[0]
    assert c.doc_id == "rozp-2015-pierwsza" and c.lokalizator == "§ 3"
    assert c.wyrozniony == "W terminie 21 dni od dnia nawiązania z ocenianym stosunku pracy"
    assert any("przygotowanego zestawu" in u for u in odp.uwagi)


def test_faq_nie_przekracza_sciezki(asystent):
    odp = asystent.odpowiedz("Kiedy stosuje się arkusz B?", "pierwsza")
    assert odp.faq_id is None or odp.faq_id.startswith(("FAQ-P", "FAQ-M"))


def test_parafrazy_pomiar(asystent):
    chybione = []
    for q in PARAFRAZY["z_bazy"]:
        if not _trafione(asystent, q["pytanie"], q["sciezka"], WZORY[q["wzor"]]["adnotacje"][0]):
            chybione.append(q["id"])
    odrzucone = sum(not asystent.odpowiedz(q["pytanie"]).znaleziono for q in PARAFRAZY["spoza_bazy"])
    n = len(PARAFRAZY["z_bazy"])
    print(f"\nparafrazy: {n - len(chybione)}/{n}; chybione: {chybione}; "
          f"spoza bazy odrzucone: {odrzucone}/{len(PARAFRAZY['spoza_bazy'])}")
    assert n - len(chybione) >= MIN_PARAFRAZ


def test_dopytanie_odnosi_sie_do_poprzedniego_pytania(asystent):
    """Karol 22.11 (wzór czatu STAGO): „a prościej?” po pytaniu o rozmowę wstępną nie kończy się brakiem źródła."""
    pierwsze = "Kiedy przeprowadza się rozmowę wstępną?"
    assert not asystent.odpowiedz("a prościej?", "pierwsza").znaleziono
    odp = asystent.odpowiedz("a prościej?", "pierwsza", poprzednie=pierwsze)
    assert odp.znaleziono and odp.pytanie == "a prościej?" and odp.cytaty


class _AtrapaUproszczenia:
    """Model w teście: przy uproszczeniu zwraca JSON z prostą wersją, cytat z pierwszego fragmentu."""

    nazwa = "atrapa"
    model = "test"

    def __init__(self):
        from kompas_core.llm import Tryb

        self.tryb = Tryb.NA_ZYWO

    def odpowiedz(self, zapytanie):
        from kompas_core.llm import Cytat, Odpowiedz

        f = zapytanie.fragmenty[0]
        tresc = '{"odpowiedz": "Rozmowę wstępną robisz na początku pracy nowej osoby."}'
        return Odpowiedz(cytaty=[Cytat(fragment_id=f.id, cytat=f.tekst[:40])], tresc=tresc)


def test_prosciej_przepisuje_odpowiedz_przez_model(asystent):
    poprzedni = asystent.dostawcy
    asystent.dostawcy = [_AtrapaUproszczenia()]
    try:
        odp = asystent.odpowiedz("a prościej?", "pierwsza", poprzednie="Kiedy przeprowadza się rozmowę wstępną?")
    finally:
        asystent.dostawcy = poprzedni
    assert odp.tresc == "Rozmowę wstępną robisz na początku pracy nowej osoby."
    assert any("Prostsza wersja" in u for u in odp.uwagi)


def test_prosciej_po_pytaniu_o_rozmowe_bierze_te_same_zrodla(asystent):
    """Serwer 22.11: „a prościej?” po „jak przeprowadzić rozmowę?” dawało brak źródła, a „wyjaśnij po ludzku”
    po pytaniu o rozmowę wstępną trafiało w inną pozycję FAQ. Uproszczenie bierze źródła poprzedniego pytania."""
    for poprzednie, dopytanie in [
        ("jak przeprowadzić rozmowę?", "a prościej?"),
        ("Kiedy przeprowadza się rozmowę wstępną?", "wyjaśnij po ludzku"),
    ]:
        wzor = asystent.odpowiedz(poprzednie, "pierwsza" if "wstępn" in poprzednie else None)
        odp = asystent.odpowiedz(dopytanie, "pierwsza" if "wstępn" in poprzednie else None, poprzednie=poprzednie)
        assert odp.znaleziono and odp.pytanie == dopytanie
        assert odp.faq_id == wzor.faq_id
        assert [c.fragment_id for c in odp.cytaty] == [c.fragment_id for c in wzor.cytaty]


class _AtrapaPodsumowania:
    """Model w teście: własne podsumowanie w "tresc", cytat z pierwszego fragmentu."""

    nazwa = "atrapa"
    model = "test"

    def __init__(self):
        from kompas_core.llm import Tryb

        self.tryb = Tryb.NA_ZYWO

    def odpowiedz(self, zapytanie):
        from kompas_core.llm import Cytat, Odpowiedz

        f = zapytanie.fragmenty[0]
        return Odpowiedz(cytaty=[Cytat(fragment_id=f.id, cytat=f.tekst[:40])], tresc="Sprzeciw wnosi oceniany.")


def test_podsumowanie_modelu_nad_zrodlami_a_bez_modelu_same_cytaty(asystent):
    """Karol 22.11: krótkie podsumowanie modelu na wierzchu, źródła pod nim; bez modelu odpowiedzią są cytaty."""
    from kompas_core.llm import Zapytanie
    from kompas_core.llm.dostawca import _wiadomosc

    pytanie = "art. 83 ustawy"
    bez_modelu = asystent.odpowiedz(pytanie, "okresowa")
    assert bez_modelu.znaleziono and bez_modelu.faq_id is None and bez_modelu.cytaty and bez_modelu.tresc is None

    poprzedni = asystent.dostawcy
    asystent.dostawcy = [_AtrapaPodsumowania()]
    try:
        odp = asystent.odpowiedz(pytanie, "okresowa")
    finally:
        asystent.dostawcy = poprzedni
    assert odp.tresc == "Sprzeciw wnosi oceniany." and odp.cytaty
    assert odp.uwagi[0].startswith("Podsumowanie napisał model AI")

    def wiersz(operacja):
        return _wiadomosc(Zapytanie(operacja=operacja, prompt_wersja="1", pytanie="?", fragmenty=[])).splitlines()[2]

    assert wiersz("asystent_formalny") == "Podsumowanie: tak"
    assert wiersz("asystent_przygotowanie") == "Podsumowanie: format z pytania"


class _AtrapaKart:
    """Model w teście: odpowiada z pierwszego fragmentu i zapamiętuje, co dostał."""

    nazwa = "atrapa"
    model = "test"

    def __init__(self):
        from kompas_core.llm import Tryb

        self.tryb = Tryb.NA_ZYWO
        self.zapytania = []

    def odpowiedz(self, zapytanie):
        from kompas_core.llm import Cytat, Odpowiedz

        self.zapytania.append(zapytanie)
        f = zapytanie.fragmenty[0]
        return Odpowiedz(
            cytaty=[Cytat(fragment_id=f.id, cytat=f.tekst[:60])],
            tresc="Cześć! Wyjaśniam zasady oceny i podpowiadam, jak wykonać czynność w aplikacji.",
        )


def test_hej_dostaje_model_z_rola_i_kartami_a_bez_modelu_zostaje_odmowa(asystent):
    """Karol 22.11: o odmowie nie decyduje lista słów. „hej” dostaje model z promptem głównym i kartami
    instrukcji aplikacji; odpowiedź ma cytat z karty. Bez modelu zostaje dotychczasowa odmowa."""
    assert not asystent.odpowiedz("hej").znaleziono

    atrapa = _AtrapaKart()
    poprzedni = asystent.dostawcy
    asystent.dostawcy = [atrapa, *poprzedni]
    try:
        odp = asystent.odpowiedz("hej")
    finally:
        asystent.dostawcy = poprzedni
    assert odp.znaleziono and odp.tresc.startswith("Cześć") and odp.cytaty[0].doc_id == "instrukcja-kompas"
    assert odp.cytaty[0].kategoria == "FUNKCJA_APLIKACJI" and odp.uwagi[0].startswith("Podsumowanie napisał model AI")
    zapytanie = atrapa.zapytania[-1]
    assert zapytanie.rola.startswith("Jesteś asystentem formalnym Kompasu Kompetencji")
    assert zapytanie.fragmenty[0].tekst.startswith("Karta 1. Co potrafi asystent")

    # Serwer 22.11: „dzięki” trafiało słowem w poradnik i dostawało przypadkowe fragmenty. Podziękowanie
    # nie niesie treści pytania, więc też idzie do modelu z kartami.
    asystent.dostawcy = [atrapa, *poprzedni]
    try:
        dzieki = asystent.odpowiedz("dzięki")
    finally:
        asystent.dostawcy = poprzedni
    assert dzieki.znaleziono and dzieki.cytaty[0].doc_id == "instrukcja-kompas"
    assert atrapa.zapytania[-1].pytanie == "dzięki"
