"""Etap cyklu oceny i następna czynność każdej osoby (#23), na danych demo z QNT i dniu 21.11.2026."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje

DZIS = date(2026, 11, 21)


@pytest.fixture(scope="module")
def klient(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("cykl")
    ust = replace(ustawienia, baza=dane / "cykl.db", log_llm=dane / "llm.jsonl")
    with TestClient(utworz_aplikacje(ust)) as k:
        k.app.state.dzis = lambda: DZIS
        yield k


@pytest.fixture(scope="module")
def h(klient):
    def zaloguj(login: str) -> dict:
        r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj


def cykl(klient, naglowek) -> dict[str, dict]:
    r = klient.get("/api/cykl", headers=naglowek)
    assert r.status_code == 200, r.text
    return {e["osoba_id"]: e for e in r.json()}


def test_przelozony_widzi_podwladnych_z_etapem_i_terminem(klient, h):
    e = cykl(klient, h("przelozony1"))
    assert set(e) == {"P-101", "P-104", "P-105", "P-202", "P-203"} | {  # + po dwie kopie testowe każdego przypadku
        "P-111", "P-114", "P-115", "P-121", "P-124", "P-125", "P-212", "P-213", "P-222", "P-223"}
    # ocena 03.12.2024 → 24 miesiące mijają 03.12.2026, czyli za 12 dni: koniec okresu
    assert (e["P-105"]["etap"], e["P-105"]["czynnosc"]) == ("ocena", "Rozmowa oceniająca")
    assert (e["P-105"]["termin"]["data"], e["P-105"]["dni_do_terminu"]) == ("2026-12-03", 12)
    assert e["P-105"]["termin"]["adnotacje"], "termin bez podstawy prawnej"
    # ocena 15.10.2025 → środek okresu, arkusz za niemal rok
    assert (e["P-104"]["etap"], e["P-104"]["czynnosc"]) == ("okres", "Okres oceny")
    assert e["P-104"]["termin"]["data"] == "2027-10-15"
    assert not any(x["po_terminie"] for x in e.values())


def test_po_ocenie_negatywnej_kryteria_w_7_dni_i_znacznik_po_terminie(klient, h):
    e = cykl(klient, h("przelozony2"))["P-102"]
    assert (e["etap"], e["czynnosc"]) == ("kryteria", "Ustal kryteria")
    assert (e["termin"]["data"], e["dni_do_terminu"]) == ("2026-11-23", 2)
    # Ponowna ocena liczy się od zapoznania z oceną negatywną; data jest w aktach (kartoteka QNT, demo).
    assert not any("zapoznania" in b for b in e["braki"])

    klient.app.state.dzis = lambda: date(2026, 11, 25)
    try:
        e = cykl(klient, h("przelozony2"))["P-102"]
    finally:
        klient.app.state.dzis = lambda: DZIS
    assert (e["dni_do_terminu"], e["po_terminie"]) == (-2, True)


def test_pierwsza_ocena_najpierw_rozmowa_wstepna_potem_ocena(klient, h):
    e = cykl(klient, h("przelozony1"))
    assert (e["P-202"]["sciezka"], e["P-202"]["etap"], e["P-202"]["czynnosc"]) == (
        "pierwsza", "kryteria", "Rozmowa wstępna")
    assert (e["P-203"]["etap"], e["P-203"]["czynnosc"]) == ("ocena", "Pierwsza ocena")
    assert e["P-203"]["termin"]["data"] == "2026-12-31"


def test_proces_w_aplikacji_przesuwa_etap(klient, h):
    r = klient.post("/api/procesy", json={"osoba_id": "P-104", "sciezka": "okresowa"}, headers=h("przelozony1"))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    e = cykl(klient, h("przelozony1"))["P-104"]
    # termin kryteriów (14.11.2025) minął przed procesem w aplikacji: dotrzymany poza nią, trwa okres oceny
    assert (e["etap"], e["proces_id"]) == ("okres", pid)

    baza = klient.app.state.baza
    for krok, czynnosc in [(3, "Rozmowa oceniająca"), (6, "Ocena na piśmie")]:
        baza.execute("UPDATE procesy SET krok = ? WHERE id = ?", (krok, pid))
        baza.commit()
        e = cykl(klient, h("przelozony1"))["P-104"]
        assert (e["etap"], e["czynnosc"]) == ("ocena", czynnosc)


def test_zakres_jak_w_liscie_pracownikow(klient, h):
    assert set(cykl(klient, h("oceniany"))) == {"P-101"}
    assert len(cykl(klient, h("hr"))) == 29


def test_okno_oceny_koncowej_z_konfiguracji(ustawienia):
    from kompas_mc.cykl import etap_okresowej
    from kompas_mc.qnt import MockQnt
    from kompas_mc.terminy_okresowej import KonfiguracjaTerminow

    konf = KonfiguracjaTerminow.z_pliku(ustawienia.terminy_okresowej)
    robert = MockQnt.z_pliku(ustawienia.qnt).pracownik("P-105")  # termin oceny 03.12.2026, za 12 dni
    assert konf.okno_oceny_koncowej.liczba == 60
    assert etap_okresowej(robert, None, konf, DZIS, DZIS).etap == "ocena"
    krotsze = konf.model_copy(update={"okno_oceny_koncowej": konf.okno_oceny_koncowej.model_copy(update={"liczba": 10})})
    assert etap_okresowej(robert, None, krotsze, DZIS, DZIS).etap == "okres"


def test_pierwsza_po_rozmowie_wstepnej_nastepne_jest_sprawozdanie(klient, h):
    """#99: po zapisie rozmowy wstępnej i terminu sprawozdania cykl pokazuje sprawozdanie i datę rozmowy."""
    naglowek = h("przelozony1")
    pid = klient.post("/api/procesy", json={"osoba_id": "P-202", "sciezka": "pierwsza"}, headers=naglowek).json()["id"]
    url = f"/api/procesy/{pid}/pierwsza-ocena"
    stan = klient.get(url, headers=naglowek).json()
    od = stan["terminy"]["termin_sprawozdania_od"]["data"]
    dane = {**stan["dane"], "data_rozmowy_wstepnej": "2026-11-20", "wyznaczony_termin_sprawozdania": od}
    assert klient.put(url, json=dane, headers=naglowek).status_code == 200
    e = cykl(klient, naglowek)["P-202"]
    assert (e["etap"], e["czynnosc"], e["termin"]["data"]) == ("okres", "Sprawozdanie pracownika", od)
    assert e["kryteria_ustalone"] == "2026-11-20", "etap rozpoczęcia z datą rozmowy wstępnej"
    assert e["termin"]["adnotacje"]
