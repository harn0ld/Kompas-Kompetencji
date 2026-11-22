"""Asystent formalny pytany bez ścieżki (okno w menu): sprzeciw od oceny okresowej to FAQ-O21, nie wpis
o pierwszej ocenie (FAQ-P27). Na serwerze testowym 22.11 pytanie o termin sprzeciwu od oceny okresowej
dostawało odpowiedź zaczynającą się od „nie ma przepisu o sprzeciwie od pierwszej oceny”."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje


@pytest.fixture(scope="module")
def klient(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("sprzeciw")
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "a.db", log_llm=dane / "l.jsonl"))) as k:
        r = k.post("/api/auth/login", json={"login": "przelozony1", "hasło": "demo"})
        yield k, {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.parametrize(("pytanie", "faq"), [
    ("W jakim terminie oceniany może wnieść sprzeciw od oceny okresowej?", "FAQ-O21"),
    ("Ile dni ma pracownik na sprzeciw od oceny okresowej?", "FAQ-O21"),
    ("Czy od pierwszej oceny przysługuje sprzeciw?", "FAQ-P27"),
])
def test_sprzeciw_bez_sciezki_trafia_we_wlasciwa_pozycje(klient, pytanie, faq):
    k, h = klient
    r = k.post("/api/asystent", headers=h, json={"pytanie": pytanie})
    assert r.status_code == 200, r.text
    assert r.json()["faq_id"] == faq


@pytest.mark.parametrize("pytanie", [
    "jak przeprowadzić rozmowę? robie to pierwszy raz, nie wiem co i jak",
    "Jak przeprowadzić rozmowę oceniającą?",
])
def test_jak_przeprowadzic_rozmowe_bez_sciezki_daje_kroki(klient, pytanie):
    """Na serwerze 22.11 te pytania trafiały w FAQ-P19 (termin pierwszej oceny) i FAQ-O09 (termin kryteriów)."""
    k, h = klient
    r = k.post("/api/asystent", headers=h, json={"pytanie": pytanie})
    assert r.status_code == 200, r.text
    assert r.json()["faq_id"] == "FAQ-R07"
    assert r.json()["tresc"].startswith("Krok po kroku")
