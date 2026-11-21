"""#82: równoczesne zapytania nie dają fałszywych 404/409/500 (jedno połączenie SQLite na wątek)."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje
from kompas_mc.baza import polacz


@pytest.fixture
def api(ustawienia, tmp_path):
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=tmp_path / "r.db", log_llm=tmp_path / "l.jsonl"))) as k:
        yield k


def test_rownolegle_odczyty_procesu_zawsze_200(api):
    t = api.post("/api/auth/login", json={"login": "przelozony1", "hasło": "demo"}).json()["token"]
    h = {"authorization": f"Bearer {t}"}
    p = api.post("/api/procesy", json={"osoba_id": "P-101", "sciezka": "okresowa"}, headers=h).json()["id"]
    d = api.get(f"/api/procesy/{p}/krok2", headers=h).json()
    wsk = {k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]] for k in d["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"}
    assert api.put(f"/api/procesy/{p}/krok2", json={"wskazniki": wsk, "dodatkowe": []}, headers=h).status_code == 200

    def zapytanie(_):
        return api.get(f"/api/procesy/{p}/ocena", headers=h).status_code

    with ThreadPoolExecutor(max_workers=16) as pula:
        kody = list(pula.map(zapytanie, range(160)))
    assert kody.count(200) == len(kody), {k: kody.count(k) for k in set(kody)}


def test_watki_maja_osobne_polaczenia_a_zapisy_sa_widoczne(tmp_path):
    baza = polacz(tmp_path / "w.db")
    with baza:
        baza.execute("CREATE TABLE t (x INTEGER)")

    def zapisz(i):
        with baza:
            baza.execute("INSERT INTO t VALUES (?)", (i,))
        return id(baza.polaczenie())

    with ThreadPoolExecutor(max_workers=8) as pula:
        polaczenia = set(pula.map(zapisz, range(200)))
    assert len(polaczenia) > 1
    assert baza.execute("SELECT COUNT(*) FROM t").fetchone() == (200,)
    assert baza.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    baza.close()
