"""„Rozpocznij od początku” dla osób demo (#186): reset danych oceny i uprawnienia."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje

CEL = {"nazwa": "Cel do skasowania", "miernik": "jeden", "termin": "2027-06-30"}


@pytest.fixture(scope="module")
def k(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("demo-od-poczatku")
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "d.db", log_llm=dane / "llm.jsonl"))) as kl:
        yield kl


@pytest.fixture(scope="module")
def h(k):
    def zaloguj(login: str) -> dict:
        r = k.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj


def _etap(k, h, osoba: str) -> dict:
    return next(e for e in k.get("/api/cykl", headers=h).json() if e["osoba_id"] == osoba)


def test_lista_pracownikow_oznacza_osoby_demo(k, h):
    ludzie = {p["osoba_id"]: p for p in k.get("/api/pracownicy", headers=h("przelozony1")).json()}
    assert ludzie["P-101"]["demo_od_poczatku"] == "okresowa"
    assert ludzie["P-203"]["demo_od_poczatku"] == "pierwsza"
    assert ludzie["P-104"]["demo_od_poczatku"] is None


@pytest.mark.parametrize(("osoba", "sciezka"), [("P-101", "okresowa"), ("P-203", "pierwsza")])
def test_reset_kasuje_proces_cele_notatki_i_historie(k, h, osoba, sciezka):
    hp = h("przelozony1")
    proces = k.post("/api/procesy", headers=hp, json={"osoba_id": osoba, "sciezka": sciezka})
    assert proces.status_code == 201, proces.text
    assert k.post(f"/api/pracownicy/{osoba}/notatki", headers=hp, json={"tresc": "Notatka z demo"}).status_code == 201
    cel = k.post(f"/api/pracownicy/{osoba}/cele", headers=hp, json=CEL)
    assert cel.status_code == 201, cel.text
    assert _etap(k, hp, osoba)["proces_id"] == proces.json()["id"]

    r = k.post(f"/api/demo/pracownicy/{osoba}/od-poczatku", headers=hp)
    assert r.status_code == 200, r.text
    assert r.json() == {"osoba_id": osoba, "sciezka": sciezka, "usuniete_procesy": 1, "usuniete_cele": 1, "usuniete_notatki": 1}

    assert not [p for p in k.get("/api/procesy", headers=hp).json() if p["osoba_id"] == osoba]
    assert k.get(f"/api/pracownicy/{osoba}/notatki", headers=hp).json() == []
    assert k.get(f"/api/pracownicy/{osoba}/cele", headers=hp).json()["cele"] == []
    assert _etap(k, hp, osoba)["proces_id"] is None

    # Ocena zaczyna się od nowa; nowy proces i cel nie dziedziczą historii po skasowanych (id mogą wrócić).
    nowy = k.post("/api/procesy", headers=hp, json={"osoba_id": osoba, "sciezka": sciezka})
    assert nowy.status_code == 201 and nowy.json()["krok"] == 1
    nowy_cel = k.post(f"/api/pracownicy/{osoba}/cele", headers=hp, json=CEL).json()
    assert len(k.get(f"/api/cele/{nowy_cel['id']}/historia", headers=hp).json()) == 1
    assert k.post(f"/api/demo/pracownicy/{osoba}/od-poczatku", headers=hp).status_code == 200


def test_reset_odnotowany_w_rejestrze_operacji(k, h):
    assert k.post("/api/demo/pracownicy/P-101/od-poczatku", headers=h("przelozony1")).status_code == 200
    wpisy = k.get("/api/rejestr", headers=h("hr"), params={"osoba": "P-101"}).json()["wpisy"]
    assert any(w["trasa"] == "/api/demo/pracownicy/{osoba_id}/od-poczatku" and w["wynik"] == "ok" for w in wpisy)


@pytest.mark.parametrize(
    ("login", "osoba", "status"),
    [
        ("przelozony1", "P-104", 403),  # podwładny bez znacznika demo
        ("przelozony2", "P-101", 403),  # cudzy podwładny
        ("hr", "P-101", 403),  # HR nie prowadzi oceny
        ("oceniany", "P-101", 403),  # oceniany nie resetuje własnej oceny
        ("przelozony1", "P-999", 404),
    ],
)
def test_odmowy(k, h, login, osoba, status):
    assert k.post(f"/api/demo/pracownicy/{osoba}/od-poczatku", headers=h(login)).status_code == status
