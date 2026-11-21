"""Cele rozwojowe (#10): przejścia statusów przy obu wartościach przełącznika, uprawnienia, historia, podpowiedzi."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from kompas_core.zrodla.cli import main as waliduj

from kompas_mc.app import utworz_aplikacje

KONF = Path(__file__).resolve().parents[2] / "konfiguracja"
CEL = {"nazwa": "Prowadzenie spotkań zespołu", "miernik": "3 spotkania z notatką", "termin": "2027-06-30"}


def _klient(ustawienia, tmp_path_factory, edycja: bool):
    dane = tmp_path_factory.mktemp("cele")
    konf = dane / "cele.yaml"
    konf.write_text(
        (KONF / "cele.yaml").read_text(encoding="utf-8").replace(
            "pracownik_moze_edytowac: true", f"pracownik_moze_edytowac: {str(edycja).lower()}"
        ),
        encoding="utf-8",
    )
    return TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "c.db", log_llm=dane / "l.jsonl", cele=konf)))


@pytest.fixture(scope="module")
def klient(ustawienia, tmp_path_factory):
    with _klient(ustawienia, tmp_path_factory, edycja=True) as k:
        yield k


@pytest.fixture(scope="module")
def klient_bez_edycji(ustawienia, tmp_path_factory):
    with _klient(ustawienia, tmp_path_factory, edycja=False) as k:
        yield k


def _h(klient, login: str) -> dict:
    r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _nowy(klient, login: str, osoba: str = "P-101", **zmiany) -> dict:
    r = klient.post(f"/api/pracownicy/{osoba}/cele", json={**CEL, **zmiany}, headers=_h(klient, login))
    assert r.status_code == 201, r.text
    return r.json()


def _status(klient, login: str, cel: dict, status: str):
    return klient.post(f"/api/cele/{cel['id']}/status", json={"status": status}, headers=_h(klient, login))


def test_konfiguracja_ma_zrodla():
    assert waliduj(["--manifest", str(KONF / "korpus.yaml"), str(KONF / "cele.yaml")]) == 0


def test_propozycja_odrzucenie_poprawka_akceptacja_z_historia(klient):
    cel = _nowy(klient, "oceniany")
    assert cel["status"] == "propozycja" and cel["autor"] == "oceniany"

    pusty = klient.post(f"/api/cele/{cel['id']}/odrzuc", json={"komentarz": "  "}, headers=_h(klient, "przelozony1"))
    assert pusty.status_code == 422
    r = klient.post(f"/api/cele/{cel['id']}/odrzuc", json={"komentarz": "Dodaj miernik liczbowy."},
                    headers=_h(klient, "przelozony1"))
    assert (r.json()["status"], r.json()["komentarz"]) == ("odrzucony", "Dodaj miernik liczbowy.")

    r = klient.put(f"/api/cele/{cel['id']}", json={**CEL, "miernik": "4 spotkania"}, headers=_h(klient, "oceniany"))
    assert r.json()["status"] == "propozycja"
    r = klient.post(f"/api/cele/{cel['id']}/zatwierdz", headers=_h(klient, "przelozony1"))
    assert r.status_code == 200 and r.json()["status"] == "zatwierdzony"

    historia = r.json()["historia"]
    assert [w["autor"] for w in historia] == ["oceniany", "przelozony1", "oceniany", "przelozony1"]
    assert historia[2]["zmiany"]["miernik"] == {"przed": "3 spotkania z notatką", "po": "4 spotkania"}


def test_zmiana_zatwierdzonego_przez_pracownika_wraca_do_propozycji(klient):
    cel = _nowy(klient, "przelozony1")
    assert cel["status"] == "zatwierdzony", "cel przełożonego nie czeka na akceptację"
    r = klient.put(f"/api/cele/{cel['id']}", json={**CEL, "nazwa": "Inny cel"}, headers=_h(klient, "oceniany"))
    assert r.json()["status"] == "propozycja"
    r = klient.put(f"/api/cele/{cel['id']}", json={**CEL, "nazwa": "Cel przełożonego"}, headers=_h(klient, "przelozony1"))
    assert r.json()["status"] == "propozycja", "zmiana przełożonego nie zmienia statusu"


def test_realizacja_zgloszenie_i_potwierdzenie_osiagniecia(klient):
    cel = _nowy(klient, "przelozony1")
    assert _status(klient, "oceniany", cel, "w_realizacji").json()["status"] == "w_realizacji"
    r = _status(klient, "oceniany", cel, "osiągnięty")
    assert r.json()["status"] == "w_realizacji" and r.json()["zgloszono_osiagniecie"], "pracownik tylko zgłasza"
    assert _status(klient, "oceniany", cel, "porzucony").status_code == 403
    assert _status(klient, "przelozony1", cel, "osiągnięty").json()["status"] == "osiągnięty"
    # stan końcowy: bez zmian treści i statusu
    assert klient.put(f"/api/cele/{cel['id']}", json=CEL, headers=_h(klient, "przelozony1")).status_code == 409
    assert _status(klient, "przelozony1", cel, "porzucony").status_code == 409
    assert klient.post(f"/api/cele/{cel['id']}/zatwierdz", headers=_h(klient, "przelozony1")).status_code == 409


def test_zakazane_przejscia(klient):
    cel = _nowy(klient, "oceniany")
    assert _status(klient, "oceniany", cel, "w_realizacji").status_code == 409, "propozycja nie jest zatwierdzona"
    assert _status(klient, "przelozony1", cel, "osiągnięty").status_code == 409
    assert klient.post(f"/api/cele/{cel['id']}/zatwierdz", headers=_h(klient, "oceniany")).status_code == 403
    assert _status(klient, "przelozony1", cel, "porzucony").json()["status"] == "porzucony"


def test_uprawnienia_i_zakres(klient):
    cel = _nowy(klient, "oceniany")
    assert klient.get("/api/pracownicy/P-101/cele", headers=_h(klient, "hr")).status_code == 200
    assert klient.post("/api/pracownicy/P-101/cele", json=CEL, headers=_h(klient, "hr")).status_code == 403
    assert klient.post(f"/api/cele/{cel['id']}/odrzuc", json={"komentarz": "x"}, headers=_h(klient, "hr")).status_code == 403
    # przełożony innego zespołu i oceniany cudzej osoby nie widzą celów
    assert klient.get("/api/pracownicy/P-101/cele", headers=_h(klient, "przelozony2")).status_code == 403
    assert klient.get("/api/pracownicy/P-104/cele", headers=_h(klient, "oceniany")).status_code == 403
    r = klient.post("/api/pracownicy/P-101/cele", json={**CEL, "wskaznik_id": "nie-ma.1"}, headers=_h(klient, "przelozony1"))
    assert r.status_code == 422


def test_bez_edycji_pracownika(klient_bez_edycji):
    k = klient_bez_edycji
    assert k.get("/api/cele/ustawienia", headers=_h(k, "oceniany")).json() == {"pracownik_moze_edytowac": False}
    assert k.post("/api/pracownicy/P-101/cele", json=CEL, headers=_h(k, "oceniany")).status_code == 403
    cel = _nowy(k, "przelozony1")
    assert k.put(f"/api/cele/{cel['id']}", json=CEL, headers=_h(k, "oceniany")).status_code == 403
    assert _status(k, "oceniany", cel, "w_realizacji").json()["status"] == "w_realizacji", "postęp nadal zgłasza pracownik"
    assert k.put(f"/api/cele/{cel['id']}", json={**CEL, "nazwa": "Zmiana"}, headers=_h(k, "przelozony1")).status_code == 200


def test_podpowiedzi_z_ostatniej_oceny_na_pismie_nic_nie_zapisuja(klient):
    h = _h(klient, "przelozony1")
    url = "/api/pracownicy/P-104/cele"
    r = klient.get(f"{url}/podpowiedzi", headers=h).json()
    assert r["podpowiedzi"] == [] and r["komunikat"], "bez oceny brak podpowiedzi"

    proces = f"/api/procesy/{klient.post('/api/procesy', json={'osoba_id': 'P-104', 'sciezka': 'okresowa'}, headers=h).json()['id']}"
    kryteria = klient.get(f"{proces}/krok2", headers=h).json()["kryteria"]
    wsk = {k["kompetencja_id"]: [k["wskazniki"][0]["wskaznik_id"]] for k in kryteria if k["rodzaj"] == "OBOWIAZKOWE"}
    assert klient.put(f"{proces}/krok2", json={"wskazniki": wsk, "dodatkowe": []}, headers=h).status_code == 200
    nisko = next(iter(wsk.values()))[0]
    przyklad = [{"sytuacja": "Projekt X", "dzialanie": "Brak notatek", "rezultat": "Opóźnienie"}]
    r = klient.put(f"{proces}/ocena/wskazniki", json={"wskazniki": {nisko: {"poziom": 3, "przyklady": przyklad}}}, headers=h)
    assert r.status_code == 200, r.text
    # ocena w toku nie jest źródłem podpowiedzi (pracownik nie widzi ocen przed sporządzeniem)
    assert klient.get(f"{url}/podpowiedzi", headers=h).json()["podpowiedzi"] == []

    baza = klient.app.state.baza
    baza.execute("UPDATE procesy SET krok = 6 WHERE id = ?", (int(proces.rsplit("/", 1)[1]),))
    baza.commit()
    for login in ("przelozony1", "hr"):
        p = klient.get(f"{url}/podpowiedzi", headers=_h(klient, login)).json()["podpowiedzi"]
        assert [x["wskaznik_id"] for x in p] == [nisko] and p[0]["poziom"] == 3
        assert "3 (poniżej oczekiwań)" in p[0]["podstawa"] and p[0]["adnotacje"]
    assert klient.get(url, headers=h).json() == [], "podpowiedzi nie tworzą celów"
