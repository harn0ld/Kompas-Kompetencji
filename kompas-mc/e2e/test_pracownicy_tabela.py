"""Test Playwright #54: Pracownicy jako tabela (sortowanie, grupowanie, filtry, kolumny, wiersz otwiera kartę).

Uruchomienie jak w test_samoocena.py (API, interfejs, zmienne KOMPAS_URL, KOMPAS_API, PLAYWRIGHT_CHROMIUM,
KOMPAS_ZRZUTY, TRYB=dark dla ciemnego motywu). Oczekiwane wartości liczone z API, nie wpisane na sztywno.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")
API = os.environ.get("KOMPAS_API", "http://127.0.0.1:8002")
ZRZUTY = Path(os.environ["KOMPAS_ZRZUTY"]) if os.environ.get("KOMPAS_ZRZUTY") else None
TRYB = os.environ.get("TRYB", "light")


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        yield p, b
        b.close()


def _dane(p, login: str) -> tuple[list[dict], dict[str, dict]]:
    """Pracownicy w zakresie konta i ich etapy z /api/cykl."""
    api = p.request.new_context()
    r = api.post(f"{API}/api/auth/login", data={"login": login, "hasło": "demo"})
    assert r.ok, r.text()
    h = {"authorization": f"Bearer {r.json()['token']}"}
    ludzie = api.get(f"{API}/api/pracownicy", headers=h).json()
    cykl = {c["osoba_id"]: c for c in api.get(f"{API}/api/cykl", headers=h).json()}
    api.dispose()
    return ludzie, cykl


def _pracownicy(b, login: str) -> Page:
    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=TRYB)
    page.goto(URL)
    page.fill('input[aria-label="Login"]', login)
    page.fill('input[aria-label="Hasło"]', "demo")
    page.click("form.logowanie-formularz button")
    page.locator("nav.menu button.poz", has_text="Pracownicy").click()
    expect(page.locator("table.tabela-pracownikow tbody tr.wiersz-osoby").first).to_be_visible()
    return page


def _zrzut(page: Page, nazwa: str) -> None:
    if ZRZUTY:
        ZRZUTY.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ZRZUTY / f"{nazwa}-{TRYB}.png"), full_page=True)


def _menu(page: Page, pigulka: str, opcja: str) -> None:
    page.locator(".listwa button.pigulka", has_text=re.compile(f"^{pigulka}")).click()
    page.locator(".panel-rozwijany button.opcja", has_text=re.compile(f"^{opcja}")).click()


def test_tabela_hr(przegladarka):
    p, b = przegladarka
    ludzie, cykl = _dane(p, "hr")
    page = _pracownicy(b, "hr")
    wiersze = page.locator("tbody tr.wiersz-osoby")
    licznik = page.locator(".licznik-osob")

    expect(wiersze).to_have_count(len(ludzie))
    expect(licznik).to_have_text(f"{len(ludzie)} z {len(ludzie)} osób")
    _zrzut(page, "pracownicy-tabela-hr")

    # Domyślnie po terminie: pierwszy wiersz to osoba z najbliższym terminem (po terminie byłaby jeszcze wyżej).
    expect(page.locator('th[aria-sort="ascending"]')).to_have_text("Termin")
    najblizszy = min(cykl.values(), key=lambda c: c["dni_do_terminu"] if c["dni_do_terminu"] is not None else 10**9)
    osoba = next(o for o in ludzie if o["osoba_id"] == najblizszy["osoba_id"])
    expect(wiersze.first.locator("td.kol-osoba")).to_contain_text(f"{osoba['imie']} {osoba['nazwisko']}")

    # Drugi klik w nagłówek odwraca kolejność.
    page.locator("thead button.sortuj", has_text="Termin").click()
    expect(page.locator('th[aria-sort="descending"]')).to_have_text("Termin")
    expect(wiersze.first).not_to_contain_text(osoba["nazwisko"])
    page.locator("thead button.sortuj", has_text="Termin").click()

    # Grupowanie po wydziale: nagłówek na każdy wydział z liczbą osób; zwinięta grupa chowa swoje wiersze.
    _menu(page, "Grupuj", "Wydział")
    wydzialy: dict[str, int] = {}
    for o in ludzie:
        wydzial = o["komorka"].split(" / ", 1)[-1]
        wydzialy[wydzial] = wydzialy.get(wydzial, 0) + 1
    grupy = page.locator("tbody tr.wiersz-grupy")
    expect(grupy).to_have_count(len(wydzialy))
    for wydzial, n in wydzialy.items():
        expect(grupy.filter(has_text=wydzial)).to_have_count(1)
    _zrzut(page, "pracownicy-tabela-hr-grupy")
    pierwsza = grupy.first.locator("button.grupa")
    n_pierwszej = int(re.search(r"(\d+) os", pierwsza.inner_text()).group(1))
    pierwsza.click()
    expect(pierwsza).to_have_attribute("aria-expanded", "false")
    expect(wiersze).to_have_count(len(ludzie) - n_pierwszej)
    pierwsza.click()
    _menu(page, "Grupuj", "Bez grupowania")
    expect(grupy).to_have_count(0)

    # Filtr etapu: liczba przy opcji, licznik i wiersze się zgadzają.
    ocena = sum(1 for c in cykl.values() if c["etap"] == "ocena")
    page.locator(".listwa button.pigulka", has_text=re.compile("^Etap")).click()
    expect(page.locator(".panel-rozwijany button.opcja", has_text="Ocena końcowa")).to_contain_text(str(ocena))
    page.locator(".panel-rozwijany button.opcja", has_text="Ocena końcowa").click()
    expect(licznik).to_have_text(f"{ocena} z {len(ludzie)} osób")
    expect(wiersze).to_have_count(ocena)
    expect(page.locator(".listwa button.pigulka.aktywna")).to_have_text("Etap: ocena końcowa")
    _zrzut(page, "pracownicy-tabela-hr-filtr")
    page.get_by_role("button", name="Pokaż wszystkich").click()
    expect(wiersze).to_have_count(len(ludzie))

    # Wybór kolumn: ukryta „Stanowisko” znika z nagłówka i zostaje ukryta po odświeżeniu (localStorage).
    page.locator(".listwa button.pigulka", has_text="Kolumny").click()
    page.locator(".panel-rozwijany").get_by_label("Stanowisko").uncheck()
    page.keyboard.press("Escape")
    expect(page.locator("thead th", has_text="Stanowisko")).to_have_count(0)
    page.reload()
    page.locator("nav.menu button.poz", has_text="Pracownicy").click()
    expect(wiersze.first).to_be_visible()
    expect(page.locator("thead th", has_text="Stanowisko")).to_have_count(0)
    page.locator(".listwa button.pigulka", has_text="Kolumny").click()
    page.locator(".panel-rozwijany").get_by_label("Stanowisko").check()
    page.keyboard.press("Escape")
    expect(page.locator("thead th", has_text="Stanowisko")).to_have_count(1)

    # Wiersz otwiera kartę: klawiatura (Enter) i klik.
    wiersze.first.focus()
    page.keyboard.press("Enter")
    expect(page.locator("h1")).to_have_text(f"{osoba['imie']} {osoba['nazwisko']}")
    page.get_by_role("button", name="Wróć").click()
    tekst = wiersze.nth(1).locator("td.kol-osoba").inner_text()
    druga = next(f"{o['imie']} {o['nazwisko']}" for o in ludzie if f"{o['imie']} {o['nazwisko']}" in tekst)
    wiersze.nth(1).click()
    expect(page.locator("h1")).to_have_text(druga)
    page.close()


def test_tabela_przelozony(przegladarka):
    p, b = przegladarka
    ludzie, _ = _dane(p, "przelozony1")
    page = _pracownicy(b, "przelozony1")
    expect(page.locator("tbody tr.wiersz-osoby")).to_have_count(len(ludzie))
    _zrzut(page, "pracownicy-tabela-przelozony1")
    _menu(page, "Grupuj", "Etap")
    expect(page.locator("tbody tr.wiersz-grupy").first).to_be_visible()
    _zrzut(page, "pracownicy-tabela-przelozony1-grupy")
    page.close()


def test_twoje_dane_otwieraja_karte_ze_wszystkimi_celami(przegladarka):
    p, b = przegladarka
    api = p.request.new_context(base_url=API)
    try:
        r = api.post("/api/auth/login", data={"login": "oceniany", "hasło": "demo"})
        assert r.ok, r.text()
        h = {"authorization": f"Bearer {r.json()['token']}"}
        ja = api.get("/api/ja", headers=h).json()
        ludzie = api.get("/api/pracownicy", headers=h).json()
        osoba = next(o for o in ludzie if o["osoba_id"] == ja["osoba_id"])
        nazwy = [f"Cel odbioru {uuid4()}" for _ in range(4)]
        for nazwa in nazwy:
            r = api.post(
                f"/api/pracownicy/{osoba['osoba_id']}/cele",
                headers=h,
                data={"nazwa": nazwa, "miernik": "1 ukończone szkolenie", "termin": "2027-06-30"},
            )
            assert r.status == 201, r.text()
    finally:
        api.dispose()

    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=TRYB)
    try:
        page.goto(URL)
        page.get_by_label("Login").fill("oceniany")
        page.get_by_label("Hasło").fill("demo")
        page.click("form.logowanie-formularz button")
        page.get_by_role("button", name="Twoje dane").click()
        expect(page.locator("h1")).to_have_text(f"{osoba['imie']} {osoba['nazwisko']}")
        expect(page.locator("table.tabela-pracownikow")).to_have_count(0)
        cele = page.locator("section.cele")
        expect(cele.get_by_role("heading", name="Cele rozwojowe")).to_be_visible()
        for nazwa in nazwy:
            expect(cele.get_by_role("button", name=re.compile(nazwa))).to_be_visible()
        expect(cele.get_by_role("button", name=re.compile(r"^Pokaż wszystkie"))).to_have_count(0)

        ostatni = cele.locator(".cel", has_text=nazwy[-1])
        przycisk = ostatni.get_by_role("button", name=re.compile(nazwy[-1]))
        przycisk.click()
        expect(przycisk).to_have_attribute("aria-expanded", "true")
        expect(ostatni.locator(".cel-cialo")).to_be_visible()
    finally:
        page.close()


def test_tysiac_osob_stronicowanie(przegladarka):
    """1000 sztucznych osób (odpowiedzi API podstawione w przeglądarce): strony po 50, grupa przechodzi na kolejną stronę."""
    _, b = przegladarka
    ludzie = [
        {
            "osoba_id": f"T-{i:04d}",
            "imie": "Osoba",
            "nazwisko": f"Testowa-{i:04d}",
            "stanowisko": "referent",
            "komorka": f"Departament {'AB'[i % 2]} / Wydział {i % 7}",
            "data_zatrudnienia": "2020-01-01",
            "ostatnia_ocena_okresowa": None,
        }
        for i in range(1000)
    ]
    cykl = [
        {
            "osoba_id": o["osoba_id"],
            "sciezka": "okresowa",
            "etap": "okres",
            "czynnosc": "Okres oceny",
            "termin": {"nazwa": "Koniec okresu", "data": "2027-06-30", "adnotacje": []},
            "dni_do_terminu": i,
            "po_terminie": False,
            "proces_id": None,
            "kryteria_ustalone": None,
            "braki": [],
        }
        for i, o in enumerate(ludzie)
    ]
    page = b.new_page(viewport={"width": 1440, "height": 900}, color_scheme=TRYB)
    page.route("**/api/pracownicy", lambda r: r.fulfill(json=ludzie))
    page.route("**/api/cykl", lambda r: r.fulfill(json=cykl))
    page.goto(URL)
    page.fill('input[aria-label="Login"]', "hr")
    page.fill('input[aria-label="Hasło"]', "demo")
    page.click("form.logowanie-formularz button")
    page.locator("nav.menu button.poz", has_text="Pracownicy").click()
    wiersze = page.locator("tbody tr.wiersz-osoby")
    strona = page.locator(".stronicowanie .meta")

    expect(page.locator(".licznik-osob")).to_have_text("1000 z 1000 osób")
    expect(wiersze).to_have_count(50)
    expect(strona).to_have_text("Strona 1 z 20")
    expect(wiersze.first).to_contain_text("Testowa-0000")
    page.get_by_role("button", name="Następna").click()
    expect(strona).to_have_text("Strona 2 z 20")
    expect(wiersze.first).to_contain_text("Testowa-0050")

    # Wyszukiwanie wraca na pierwszą stronę i chowa stronicowanie, gdy wynik mieści się na jednej.
    page.get_by_label("Szukaj pracownika").fill("Testowa-099")
    expect(wiersze).to_have_count(10)
    expect(page.locator(".stronicowanie")).to_have_count(0)
    page.get_by_label("Szukaj pracownika").fill("")

    # Wydział 0 w Departamencie A ma 72 osoby: na drugiej stronie jego nagłówek wraca jako „ciąg dalszy”.
    _menu(page, "Grupuj", "Wydział")
    expect(strona).to_have_text("Strona 1 z 20")  # nagłówki grup nie zajmują miejsc wierszy
    expect(wiersze).to_have_count(50)
    page.get_by_role("button", name="Następna").click()
    expect(page.locator("tbody tr.wiersz-grupy").first).to_contain_text("Wydział 0 (ciąg dalszy)")
    _zrzut(page, "pracownicy-tabela-1000-strona2-grupy")
    page.close()


def test_filtr_z_zespolu_jako_znacznik(przegladarka):
    """Komórka wybrana w Zespole trafia do tabeli jako znacznik; zdjęcie znacznika przywraca wszystkich."""
    p, b = przegladarka
    ludzie, _ = _dane(p, "hr")
    page = _pracownicy(b, "hr")
    page.locator("nav.menu button.poz", has_text="Zespół").click()
    # #91: komórkę wybiera się w Strukturze (zakres całej strony), do Pracowników prowadzi liczba osób do zrobienia.
    wiersz = page.locator(".wiersz-departamentu button.zakres").first
    departament = wiersz.locator(".nazwa-zakresu").inner_text().strip()
    wiersz.click()
    page.locator("button.liczba-zespolu", has_text="Do zrobienia teraz").click()
    w_departamencie = sum(1 for o in ludzie if o["komorka"].split(" / ")[0] == departament)
    znacznik = page.locator(".listwa button.znacznik-filtra")
    expect(znacznik).to_have_text(departament)
    expect(page.locator(".licznik-osob")).to_have_text(f"{w_departamencie} z {len(ludzie)} osób")
    znacznik.click()
    expect(znacznik).to_have_count(0)
    expect(page.locator("tbody tr.wiersz-osoby")).to_have_count(len(ludzie))
    page.close()
