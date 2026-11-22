import json

import pytest

from kompas_mc.ustawienia import PORT_DOMYSLNY

BRAK = "brak wystarczających informacji w bazie wiedzy"


def test_zdrowie(klient):
    r = klient.get("/api/zdrowie").json()
    assert r["wersja"] == "mc-bdg" and r["port"] == PORT_DOMYSLNY == 8002
    assert r["dokumenty"] == 14 and r["fragmenty"] > 1000  # 12 z paczki MC + ustawa (#74) + instrukcja obsługi (#199)


def test_zrodla_raportuja_duplikat_i_pominiete(klient):
    r = klient.get("/api/zrodla").json()
    assert r["duplikaty"][0]["potwierdzony"] is True
    assert {p["plik"] for p in r["pominiete"]} == {"Kompas Kompetencji_ Ścieżki Oceny.png"}


@pytest.mark.parametrize("sciezka", [None, "pierwsza"])
def test_asystent_rozmowa_wstepna_cytuje_par_3_rozp_2015(klient, naglowek, sciezka):
    r = klient.post("/api/asystent", headers=naglowek("przelozony1"), json={"pytanie": "Kiedy przeprowadza się rozmowę wstępną?", "sciezka": sciezka}
    ).json()
    assert r["znaleziono"] is True and r["tryb"] == "EKSTRAKCYJNE"
    pierwszy = r["cytaty"][0]
    assert pierwszy["doc_id"] == "rozp-2015-pierwsza"
    assert pierwszy["lokalizator"] == "§ 3"
    assert pierwszy["kategoria"] == "PRZEPIS"
    assert "przeprowadza z ocenianym rozmowę wstęp" in pierwszy["cytat"]


@pytest.mark.parametrize("pytanie", [
    "Jaka jest stolica Australii?",
    "Jak ugotować bigos?",
    "Ile wynosi przepisowa prędkość na autostradzie?",
])
def test_asystent_pytanie_spoza_bazy(klient, naglowek, pytanie):
    r = klient.post("/api/asystent", headers=naglowek("przelozony1"), json={"pytanie": pytanie}).json()
    assert r["znaleziono"] is False and r["komunikat"] == BRAK and r["cytaty"] == []


def test_asystent_filtruje_sciezke(klient, naglowek):
    r = klient.post("/api/asystent", headers=naglowek("przelozony1"),
        json={"pytanie": "Ile kryteriów dodatkowych można wybrać?", "sciezka": "okresowa"},
    ).json()
    assert r["cytaty"][0]["lokalizator"] == "§ 5 ust. 2"
    assert all(not c["doc_id"].endswith("pierwsza") for c in r["cytaty"])


def test_wywolanie_jest_logowane(klient, naglowek, ustawienia):
    klient.post("/api/asystent", headers=naglowek("przelozony1"), json={"pytanie": "Kiedy przeprowadza się rozmowę wstępną?"})
    wpis = json.loads(ustawienia.log_llm.read_text(encoding="utf-8").splitlines()[-1])
    assert wpis["tryb"] == "EKSTRAKCYJNE" and wpis["walidacja_ok"] is True and wpis["fragment_ids"]


def test_baza_osobna_dla_wersji(klient, ustawienia):
    assert ustawienia.baza.exists()
    wiersze = dict(klient.app.state.baza.execute("SELECT klucz, wartosc FROM meta"))
    assert wiersze["wersja_aplikacji"] == "mc-bdg"


def test_asystent_tylko_po_zalogowaniu_i_z_limitem(klient, naglowek):
    """Helix G3 (Grok, 3): publiczny serwer, płatny model – bez logowania 401, ponad limit na konto 429."""
    from kompas_mc.app import LIMIT_ASYSTENTA

    pytanie = {"pytanie": "Ile kryteriów dodatkowych można wybrać?", "sciezka": "okresowa"}
    assert klient.post("/api/asystent", json=pytanie).status_code == 401
    h = naglowek("oceniany")
    kody = [klient.post("/api/asystent", headers=h, json=pytanie).status_code for _ in range(LIMIT_ASYSTENTA + 1)]
    assert kody[:-1] == [200] * LIMIT_ASYSTENTA and kody[-1] == 429


def test_limit_asystenta_rownolegle(klient, naglowek):
    """Przegląd bezpieczeństwa: równoległe pytania z jednego konta nie przekraczają limitu (blokada)."""
    from concurrent.futures import ThreadPoolExecutor

    from kompas_mc.app import LIMIT_ASYSTENTA

    h = naglowek("hr")
    pytanie = {"pytanie": "Ile kryteriów dodatkowych można wybrać?", "sciezka": "okresowa"}
    with ThreadPoolExecutor(8) as pula:
        kody = list(pula.map(lambda _: klient.post("/api/asystent", headers=h, json=pytanie).status_code,
                             range(LIMIT_ASYSTENTA + 10)))
    assert kody.count(200) == LIMIT_ASYSTENTA and kody.count(429) == 10
