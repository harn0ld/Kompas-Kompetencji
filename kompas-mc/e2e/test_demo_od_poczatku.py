"""Test Playwright (#186): „Rozpocznij od początku” na pulpicie przełożonego dla osób demo.

Mały przycisk „Demo: rozpocznij od początku” w linii imienia jest tylko przy Annie Zielińskiej-Demo (ocena okresowa) i Zofii Szymańskiej-Demo (pierwsza ocena).
Kliknięcie bez potwierdzenia kasuje proces Anny i otwiera ekran „Rozpoczęcie oceny” (#208). Test sam zakłada proces
przez API, więc działa na świeżej bazie i po innych testach. Uruchomienie i zmienne jak w test_samoocena.py.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest
from playwright.sync_api import expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")
API = os.environ.get("KOMPAS_API", "http://127.0.0.1:8002")


def _api(metoda: str, sciezka: str, token: str | None = None, dane: object = None):
    zadanie = urllib.request.Request(
        API + sciezka, method=metoda, data=json.dumps(dane).encode() if dane is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(zadanie) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        yield b
        b.close()


def test_rozpocznij_od_poczatku_kasuje_proces_osoby_demo(przegladarka):
    token = _api("POST", "/api/auth/login", dane={"login": "przelozony1", "hasło": "demo"})[1]["token"]
    status, _ = _api("POST", "/api/procesy", token, {"osoba_id": "P-101", "sciezka": "okresowa"})
    assert status in (201, 409)  # 409: proces Anny już jest w toku
    assert any(p["osoba_id"] == "P-101" for p in _api("GET", "/api/procesy", token)[1])

    page = przegladarka.new_page(viewport={"width": 1440, "height": 900})
    page.goto(URL)
    page.fill('input[aria-label="Login"]', "przelozony1")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.keyboard.press("Enter")
    page.wait_for_selector(".pulpit .lista .pozycja")

    przyciski = page.get_by_role("button", name="Demo: rozpocznij od początku")
    anna = page.locator(".pozycja.z-akcja", has_text="Anna Zielińska-Demo")
    expect(anna).to_have_count(1)
    expect(page.locator(".pozycja.z-akcja", has_text="Zofia Szymańska-Demo")).to_have_count(1)
    expect(przyciski).to_have_count(page.locator(".pozycja.z-akcja").count())

    # Mały przycisk w linii imienia, za plakietką terminu; wiersz osoby demo nie jest wyższy od zwykłego.
    przycisk = anna.get_by_role("button", name="Demo: rozpocznij od początku").bounding_box()
    imie = anna.get_by_role("button", name="Anna Zielińska-Demo").bounding_box()
    plakietka = anna.locator(".status").bounding_box()
    assert plakietka["x"] + plakietka["width"] <= przycisk["x"], "przycisk za plakietką"
    srodek = przycisk["y"] + przycisk["height"] / 2
    assert imie["y"] <= srodek <= imie["y"] + imie["height"], "przycisk w linii imienia"
    assert przycisk["height"] <= 32
    zwykly = page.locator(".pulpit .lista button.pozycja").first.bounding_box()
    assert anna.bounding_box()["height"] <= zwykly["height"] + 2, "wiersz demo tej samej wysokości"

    # Bez okna potwierdzenia (#208): kliknięcie kasuje dane i od razu otwiera „Rozpoczęcie oceny” (krok 1).
    dialogi: list[str] = []
    page.on("dialog", lambda d: (dialogi.append(d.message), d.dismiss()))
    anna.get_by_role("button", name="Demo: rozpocznij od początku").click()
    expect(page.get_by_text("Rozpoczęcie oceny · zanim ocenisz")).to_be_visible()
    expect(page.get_by_role("heading", name="Anna Zielińska-Demo")).to_be_visible()
    expect(page.get_by_role("button", name="Rozpocznij ocenę")).to_be_visible()
    assert dialogi == []
    assert not any(p["osoba_id"] == "P-101" for p in _api("GET", "/api/procesy", token)[1])
    # „Wróć” prowadzi do karty osoby.
    page.get_by_role("button", name="Wróć").first.click()
    expect(page.get_by_text("Ocena okresowa", exact=False).first).to_be_visible()
    page.close()
