"""Mapa kompetencji zespołu (#33): zakres per rola, HR bez treści, bieżąca ocena zamiast ostatniej z kartoteki."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje
from kompas_mc.qnt import MockQnt


@pytest.fixture(scope="module")
def k(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("zespol")
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "z.db", log_llm=dane / "llm.jsonl"))) as kl:
        yield kl


@pytest.fixture(scope="module")
def h(k):
    def zaloguj(login: str) -> dict:
        r = k.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj


def test_oceny_czastkowe_zgodne_z_wynikiem(ustawienia):
    """Dane demo: negatywna = któreś kryterium 1 albo średnia < 4 (konfiguracja/wynik-okresowy.yaml)."""
    for p in MockQnt.z_pliku(ustawienia.qnt).pracownicy:
        o = p.ostatnia_ocena_okresowa
        if not o or not o.oceny_czastkowe:
            continue
        pkt = list(o.oceny_czastkowe.values())
        negatywna = 1 in pkt or sum(pkt) / len(pkt) < 4
        assert (o.wynik == "negatywna") == negatywna, p.osoba_id
        assert set(pkt) <= {1, 3, 5, 7, 9}


def test_przelozony_widzi_podwladnych_z_kartoteki(k, h):
    r = k.get("/api/zespol/kompetencje", headers=h("przelozony1"))
    assert r.status_code == 200
    m = r.json()
    assert m["skala"] == [1, 3, 5, 7, 9] and m["poziom_oczekiwan"] == 5
    osoby = {o["osoba_id"]: o for o in m["osoby"]}
    assert set(osoby) == {"P-101", "P-104", "P-105", "P-111", "P-114", "P-115", "P-121", "P-124", "P-125"}  # pierwsza ocena (P-2xx): bez oceny
    assert osoby["P-104"]["zrodlo"] == "ostatnia_ocena" and osoby["P-104"]["punkty"]["komunikacja"] == 3
    nazwy = {kr["kompetencja_id"]: kr["nazwa"] for kr in m["kryteria"]}
    assert "komunikacja" in nazwy and "zarzadzanie-ludzmi" in nazwy  # arkusz C i B naczelnika


def test_hr_bez_tresci_ocen(k, h):
    assert k.get("/api/zespol/kompetencje", headers=h("hr")).status_code == 403
    assert "oceny_czastkowe" not in k.get("/api/pracownicy", headers=h("hr")).text
    assert "oceny_czastkowe" not in k.get("/api/pracownicy", headers=h("przelozony1")).text
    assert k.get("/api/zespol/kompetencje").status_code == 401


def test_oceniany_widzi_tylko_siebie(k, h):
    osoby = k.get("/api/zespol/kompetencje", headers=h("oceniany")).json()["osoby"]
    assert [o["osoba_id"] for o in osoby] == ["P-101"]


def test_biezaca_ocena_zastepuje_kartoteke(k, h):
    hp = h("przelozony2")
    pr = k.post("/api/procesy", json={"osoba_id": "P-103", "sciezka": "okresowa"}, headers=hp).json()
    k2 = k.get(f"/api/procesy/{pr['id']}/krok2", headers=hp).json()
    wsk = {kr["kompetencja_id"]: [w["wskaznik_id"] for w in kr["wskazniki"][:1]] for kr in k2["kryteria"] if kr["rodzaj"] == "OBOWIAZKOWE"}
    assert k.put(f"/api/procesy/{pr['id']}/krok2", json={"wskazniki": wsk}, headers=hp).status_code == 200
    stan = k.get(f"/api/procesy/{pr['id']}/ocena", headers=hp).json()
    kr = stan["kryteria"][0]
    w = kr["wskazniki"][0]["wskaznik_id"]
    k.put(f"/api/procesy/{pr['id']}/ocena/wskazniki", headers=hp, json={"wskazniki": {w: {"poziom": 9, "przyklady": [
        {"sytuacja": "S", "dzialanie": "D", "rezultat": "R"}]}}})
    r = k.put(f"/api/procesy/{pr['id']}/ocena/decyzje", headers=hp, json={"decyzje": {kr["kompetencja_id"]: {"punkty": 9}}})
    assert r.status_code == 200, r.text
    osoby = {o["osoba_id"]: o for o in k.get("/api/zespol/kompetencje", headers=hp).json()["osoby"]}
    assert osoby["P-103"]["zrodlo"] == "biezaca_ocena"
    assert osoby["P-103"]["punkty"] == {kr["kompetencja_id"]: 9}
    assert osoby["P-102"]["zrodlo"] == "ostatnia_ocena" and osoby["P-102"]["punkty"]["rzetelnosc"] == 1
