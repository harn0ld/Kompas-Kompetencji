"""Test Playwright (#186): „Rozpocznij od początku” na pulpicie przełożonego dla osób demo.

Przycisk jest tylko przy Annie Zielińskiej-Demo (ocena okresowa) i Zofii Szymańskiej-Demo (pierwsza ocena).
Po potwierdzeniu proces Anny znika z bazy, a wiersz wraca do pierwszego etapu. Test sam zakłada proces
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

    przyciski = page.get_by_role("button", name="Rozpocznij od początku")
    anna = page.locator(".pulpit-wiersz-demo", has_text="Anna Zielińska-Demo")
    expect(anna).to_have_count(1)
    expect(page.locator(".pulpit-wiersz-demo", has_text="Zofia Szymańska-Demo")).to_have_count(1)
    expect(przyciski).to_have_count(page.locator(".pulpit-wiersz-demo").count())

    # Przycisk w wierszu nie zasłania tekstu i nie otwiera karty osoby.
    wiersz = anna.locator("button.pozycja").bounding_box()
    przycisk = anna.get_by_role("button", name="Rozpocznij od początku").bounding_box()
    opis = anna.locator(".pozycja-srodek").bounding_box()
    assert wiersz["y"] <= przycisk["y"] and przycisk["y"] + przycisk["height"] <= wiersz["y"] + wiersz["height"]
    assert opis["y"] + opis["height"] <= przycisk["y"], "przycisk pod opisem, nie na tekście"
    assert przycisk["x"] + przycisk["width"] < wiersz["x"] + wiersz["width"] - 48, "przycisk nie zachodzi na strzałkę"

    page.once("dialog", lambda d: d.accept())
    anna.get_by_role("button", name="Rozpocznij od początku").click()
    expect(page.get_by_role("status")).to_contain_text("Anna Zielińska-Demo: ocenę okresową zaczynasz od pierwszego etapu")
    expect(page.locator(".pulpit-wiersz-demo", has_text="Anna Zielińska-Demo")).to_be_visible()
    expect(page.locator(".powloka .karta, .karta-pracownika")).to_have_count(0)
    assert not any(p["osoba_id"] == "P-101" for p in _api("GET", "/api/procesy", token)[1])
    page.close()
