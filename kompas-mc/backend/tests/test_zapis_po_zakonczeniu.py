"""#114: spóźniony zapis nie zmienia zakończonego procesu; ponowny zapis kryteriów unieważnia decyzje."""

from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from kompas_mc import krok2_api, ocena_api
from kompas_mc.app import utworz_aplikacje


@pytest.fixture
def api(ustawienia, tmp_path):
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=tmp_path / "z.db", log_llm=tmp_path / "l.jsonl"))) as k:
        t = k.post("/api/auth/login", json={"login": "przelozony1", "hasło": "demo"}).json()["token"]
        k.headers["authorization"] = f"Bearer {t}"
        yield k


def _wskazniki(api, p):
    d = api.get(f"/api/procesy/{p}/krok2").json()
    return {k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"][:2]] for k in d["kryteria"]
            if k["rodzaj"] == "OBOWIAZKOWE"}


def _proces_z_decyzjami(api) -> tuple[int, dict]:
    p = api.post("/api/procesy", json={"osoba_id": "P-101", "sciezka": "okresowa"}).json()["id"]
    wsk = _wskazniki(api, p)
    assert api.put(f"/api/procesy/{p}/krok2", json={"wskazniki": wsk}).status_code == 200
    oceny = {w: {"poziom": 7, "uwagi": "Przykład."} for ws in wsk.values() for w in ws}
    assert api.put(f"/api/procesy/{p}/ocena/wskazniki", json={"wskazniki": oceny}).status_code == 200
    decyzje = {k: {"punkty": 7} for k in wsk}
    r = api.put(f"/api/procesy/{p}/ocena/decyzje", json={"decyzje": decyzje})
    assert r.status_code == 200 and r.json()["kompletnosc"]["kryteria_z_decyzja"] == len(wsk)
    return p, wsk


def _zakoncz_w_trakcie(monkeypatch, modul):
    """Zapis odczytuje proces w toku, a zanim zapisze, równoległe zakończenie zmienia status w bazie."""
    oryginal = modul.wczytaj_proces
    wywolano = []

    def odczyt_i_zakonczenie(baza, proces_id):
        proces = oryginal(baza, proces_id)
        if not wywolano:
            wywolano.append(proces_id)
            with baza:
                baza.execute("UPDATE procesy SET status = 'ZAKONCZONY', krok = 8 WHERE id = ?", (proces_id,))
        return proces

    monkeypatch.setattr(modul, "wczytaj_proces", odczyt_i_zakonczenie)


def _wiersz(api, p):
    return api.app.state.baza.execute(
        "SELECT status, krok, krok2, oceny_wskaznikow, decyzje, rozmowa FROM procesy WHERE id = ?", (p,)
    ).fetchone()


@pytest.mark.parametrize("sciezka, body", [
    ("decyzje", lambda wsk: {"decyzje": {k: {"punkty": 1} for k in wsk}}),
    ("wskazniki", lambda wsk: {"wskazniki": {w: {"poziom": 1} for ws in wsk.values() for w in ws}}),
    ("rozmowa", lambda wsk: {"notatki": {"cele": "Spóźniona notatka."}}),
])
def test_spozniony_zapis_oceny_409_bez_zmiany(api, monkeypatch, sciezka, body):
    p, wsk = _proces_z_decyzjami(api)
    przed = _wiersz(api, p)
    _zakoncz_w_trakcie(monkeypatch, ocena_api)
    r = api.put(f"/api/procesy/{p}/ocena/{sciezka}", json=body(wsk))
    assert r.status_code == 409, r.text
    assert _wiersz(api, p)[2:] == przed[2:]
    assert _wiersz(api, p)[:2] == ("ZAKONCZONY", 8)


def test_spozniony_zapis_kryteriow_409_bez_zmiany(api, monkeypatch):
    p, wsk = _proces_z_decyzjami(api)
    przed = _wiersz(api, p)
    _zakoncz_w_trakcie(monkeypatch, krok2_api)
    assert api.put(f"/api/procesy/{p}/krok2", json={"wskazniki": wsk}).status_code == 409
    assert _wiersz(api, p)[2:] == przed[2:]


def test_spozniona_data_zapoznania_409_bez_zmiany(api, monkeypatch):
    p, _ = _proces_z_decyzjami(api)
    przed = _wiersz(api, p)
    _zakoncz_w_trakcie(monkeypatch, krok2_api)
    r = api.put(f"/api/procesy/{p}/krok2/zapoznanie", json={"data": date.today().isoformat()})
    assert r.status_code == 409, r.text
    assert _wiersz(api, p)[2:] == przed[2:]


def test_ponowny_zapis_kryteriow_uniewaznia_decyzje_i_cofa_krok(api):
    p, wsk = _proces_z_decyzjami(api)
    assert api.get(f"/api/procesy/{p}").json()["krok"] == 5
    assert api.put(f"/api/procesy/{p}/krok2", json={"wskazniki": wsk}).status_code == 200
    stan = api.get(f"/api/procesy/{p}/ocena").json()
    assert stan["kompletnosc"]["kryteria_z_decyzja"] == 0
    assert all(k["decyzja"] is None for k in stan["kryteria"])
    assert api.get(f"/api/procesy/{p}").json()["krok"] == 3
    # oceny wskaźników zostają, więc nowa decyzja jest liczona od nowa i znów kończy krok 5
    r = api.put(f"/api/procesy/{p}/ocena/decyzje", json={"decyzje": {k: {"punkty": 7} for k in wsk}})
    assert r.json()["kompletnosc"]["kryteria_z_decyzja"] == len(wsk)
    assert api.get(f"/api/procesy/{p}").json()["krok"] == 5
