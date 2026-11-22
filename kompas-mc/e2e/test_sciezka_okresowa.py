"""Ocena okresowa od karty do PDF wyłącznie klikaniem (jak jury), bez zapisów przez API.

Część I („Rozpocznij ocenę”, rozp. 2016 § 5–7): Piotr Nowak-Demo (P-102, przełożony 2) jest w etapie kryteriów.
Karta → krok 1 → kryteria z jednym dodatkowym → PDF części I → „Zapisz i zakończ część I” → karta pokazuje okres oceny.

Część II („Zakończ ocenę”, § 10–11): Anna Zielińska-Demo (P-101, przełożony 1) jest w oknie oceny końcowej bez
procesu w aplikacji, więc „Zakończ ocenę” zaczyna od kroku 1. Krok 1 → kryteria (jedno dodatkowe) → karta →
„Zakończ ocenę” → rozmowa oceniająca jednym przebiegiem (wskaźniki z wyborem zachowania, rozwój) →
podsumowanie z punktami po rozmowie (sugestia raz przyjęta, raz zmieniona z uzasadnieniem) → „Zakończ rozmowę” →
część 3 „Ocena na piśmie” (wnioski IPRZ, poziom poprzedniej oceny) → zatwierdzenie → PDF → EZD próbnie →
zakończenie z datą zapoznania (§ 12) → karta z „Rozpocznij ocenę” i nową oceną w „Poprzednich ocenach”.
Wersja aplikacji: integracja 8164b92 (rozmowa z gałęzi 46-rozmowa-przebieg).

Świeża baza (KOMPAS_MC_DANE=$(mktemp -d)); zmienne jak w test_samoocena.py, TRYB=dark dla ciemnego motywu.
Każdy błąd JS i każda odpowiedź API ≥ 400 kończy test z komunikatem (lista w KOMPAS_ZRZUTY/bledy-<tryb>.json).
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

URL = os.environ.get("KOMPAS_URL", "http://127.0.0.1:5174")
ZRZUTY = Path(os.environ["KOMPAS_ZRZUTY"]) if os.environ.get("KOMPAS_ZRZUTY") else None
TRYB = os.environ.get("TRYB", "light")
PRZYKLAD = "Awaria systemu EZD: koordynowała zespół, przywrócenie pracy w 2 godziny."
UZASADNIENIE = "Na rozmowie omówiliśmy dodatkowe przykłady z drugiego półrocza."
IPRZ = "Szkolenie z zarządzania projektami do VI 2027; udział w zespole ds. EZD."


@pytest.fixture(scope="module")
def przegladarka():
    with sync_playwright() as p:
        sciezka = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(executable_path=sciezka) if sciezka else p.chromium.launch()
        yield b
        b.close()


class Przebieg:
    """Strona z dziennikiem błędów JS i odpowiedzi API ≥ 400 oraz numerowanymi zrzutami."""

    def __init__(self, b, login: str):
        # Ograniczony ruch: zrzut nie łapie ekranu w połowie animacji wejścia.
        self.page: Page = b.new_page(
            viewport={"width": 1440, "height": 900}, color_scheme=TRYB, reduced_motion="reduce", accept_downloads=True
        )
        self.bledy: list[str] = []
        self.page.on("pageerror", lambda e: self.bledy.append(f"JS: {e}"))
        self.page.on("console", lambda m: m.type == "error" and self.bledy.append(f"konsola: {m.text}"))
        self.page.on(
            "response",
            lambda r: r.status >= 400 and "/api/" in r.url and self.bledy.append(f"API {r.status} {r.request.method} {r.url}"),
        )
        self.page.goto(URL)
        self.page.fill('input[aria-label="Login"]', login)
        self.page.fill('input[aria-label="Hasło"]', "demo")
        self.page.click("form.logowanie-formularz button")
        self.page.wait_for_selector(".powloka")

    def krok(self, nazwa: str) -> None:
        """Zrzut całej strony i kontrola, że do tej chwili nie było błędu."""
        self.page.wait_for_load_state("networkidle")
        if ZRZUTY:
            ZRZUTY.mkdir(parents=True, exist_ok=True)
            Przebieg.nr += 1
            self.page.screenshot(path=str(ZRZUTY / f"{Przebieg.nr:02d}-{nazwa}-{TRYB}.png"), full_page=True)
            (ZRZUTY / f"bledy-{TRYB}.json").write_text(json.dumps(Przebieg.wszystkie + self.bledy, ensure_ascii=False, indent=1))
        assert not self.bledy, f"Błędy przed krokiem „{nazwa}”: {self.bledy}"

    def pdf(self, przycisk: str) -> bytes:
        with self.page.expect_download() as d:
            self.page.get_by_role("button", name=przycisk).click()
        tresc = Path(d.value.path()).read_bytes()
        assert tresc.startswith(b"%PDF"), f"„{przycisk}” nie dał PDF: {tresc[:40]!r}"
        assert len(tresc) > 1024, f"„{przycisk}”: PDF ma tylko {len(tresc)} B"
        if ZRZUTY:
            (ZRZUTY / f"{d.value.suggested_filename.removesuffix('.pdf')}-{TRYB}.pdf").write_bytes(tresc)
        return tresc

    def zamknij(self) -> None:
        Przebieg.wszystkie += self.bledy
        self.page.close()

    nr = 0
    wszystkie: list[str] = []


# Nagłówki kroków 1–2: dawniej „Krok N z 8”, od przebudowy „Rozpoczęcie oceny · …” (część I arkusza).
KROK_1 = re.compile(r"^(Krok 1 z 8|Rozpoczęcie oceny · zanim ocenisz)")
KROK_2 = re.compile(r"^(Krok 2 z 8|Rozpoczęcie oceny · kryteria)")


def _karta(page: Page, nazwisko: str) -> None:
    page.locator("nav.menu button.poz", has_text="Pulpit").click()
    page.locator(".lista button.pozycja", has_text=nazwisko).first.click()
    expect(page.locator(".karta-glowa h1")).to_contain_text(nazwisko)


def _kryteria_z_jednym_dodatkowym(page: Page) -> str:
    """Krok 2: zostawia obowiązkowe z wskaźnikami systemu, wybiera pierwsze dodatkowe, zwraca jego nazwę."""
    expect(page.get_by_text(KROK_2)).to_be_visible()
    dodatkowe = page.locator('.k2-wiersz button.k2-glowa[role="checkbox"]')
    expect(dodatkowe.first).to_be_visible()
    pierwsze = dodatkowe.first
    nazwa = pierwsze.locator(".k2-nazwa").evaluate("e => e.firstChild.textContent").strip()
    pierwsze.click()
    expect(pierwsze).to_have_attribute("aria-checked", "true")
    return nazwa


def test_ocena_okresowa_klikaniem_od_karty_do_pdf(przegladarka):
    # ── Część I: Piotr Nowak-Demo, „Rozpocznij ocenę” ──────────────────────────────────────────────
    s = Przebieg(przegladarka, "przelozony2")
    page = s.page
    s.krok("I-pulpit")
    _karta(page, "Nowak")
    nastepny = page.locator(".ramka.nastepny")
    expect(nastepny.get_by_role("button")).to_have_text("Rozpocznij ocenę")
    s.krok("I-karta-nowak")
    nastepny.get_by_role("button", name="Rozpocznij ocenę").click()

    expect(page.get_by_text(KROK_1)).to_be_visible()
    start = page.locator("form.k1-start")
    expect(start.get_by_role("button", name=re.compile("ocena okresowa", re.I))).to_have_attribute("aria-pressed", "true")
    s.krok("I-krok1")
    start.get_by_role("button", name="Rozpocznij ocenę").click()

    _kryteria_z_jednym_dodatkowym(page)
    s.krok("I-krok2-kryteria")
    page.get_by_role("button", name="Zatwierdź kryteria i dalej").click()
    # Część I arkusza (§ 5 ust. 3, § 6): wydruk do podpisu, data rozmowy i zapoznania (domyślnie dziś), zakończenie.
    expect(page.get_by_role("heading", name="Rozmowa 1: ustalenia na okres oceny")).to_be_visible()
    s.krok("I-krok2-czesc-I")
    s.pdf("Pobierz część I do podpisu")
    page.get_by_role("button", name="Zapisz i zakończ część I").click()
    expect(page.get_by_role("heading", name="Rozmowa 1 zakończona: ustalenia na okres")).to_be_visible()
    s.krok("I-czesc-I-zakonczona")

    page.get_by_role("button", name="Wróć do pracownika").click()
    expect(page.locator(".cykl li.biezacy")).to_contain_text("Okres oceny")
    expect(page.locator(".ramka.nastepny").get_by_role("button")).to_have_count(0)
    s.krok("I-karta-okres-oceny")
    s.zamknij()

    # ── Część II: Anna Zielińska-Demo, „Zakończ ocenę” ─────────────────────────────────────────────
    s = Przebieg(przegladarka, "przelozony1")
    page = s.page
    s.krok("II-pulpit")
    _karta(page, "Zielińska")
    nastepny = page.locator(".ramka.nastepny")
    expect(nastepny.get_by_role("button")).to_have_text("Zakończ ocenę")
    s.krok("II-karta-zielinska")
    nastepny.get_by_role("button", name="Zakończ ocenę").click()

    rozmowa = page.get_by_role("heading", level=1, name="Rozmowa oceniająca")
    krok1 = page.get_by_text(KROK_1)
    expect(krok1.or_(rozmowa)).to_be_visible()
    # Na świeżej bazie Zielińska nie ma procesu (kryteria przepisuje się z części I). W pełnym zestawie e2e proces
    # zakłada wcześniej test_samoocena – wtedy „Zakończ ocenę” od razu otwiera rozmowę (#72) i krok 1–2 odpada.
    dodatkowe = None
    if krok1.is_visible():
        expect(page.locator("form.k1-start")).to_be_visible()
        s.krok("II-krok1")
        page.locator("form.k1-start").get_by_role("button", name="Rozpocznij ocenę").click()
        dodatkowe = _kryteria_z_jednym_dodatkowym(page)
        s.krok("II-krok2-kryteria")
        page.get_by_role("button", name="Zatwierdź kryteria i dalej").click()
        # Koniec okresu: kryteria przepisane z podpisanej części I, data jej zapoznania z początku okresu.
        # Jedno kliknięcie: zapis daty z podpisanej części I i od razu rozmowa oceniająca (Karol 22.11, 02:04).
        expect(page.get_by_role("heading", name="Ustalenia z podpisanej części I")).to_be_visible()
        page.get_by_label("Data rozmowy i zapoznania z kryteriami (§ 6 ust. 2)").fill("2024-12-20")
        s.krok("II-czesc-I-przepisana")
        page.get_by_role("button", name="Zapisz i przejdź do rozmowy oceniającej").click()
        expect(rozmowa).to_be_visible()
        s.krok("II-rozmowa-wejscie")

        # Powrót na kartę: po części I „Zakończ ocenę” ma prowadzić do rozmowy oceniającej (część II).
        _karta(page, "Zielińska")
        expect(page.locator(".cykl li.zrobiony").first).to_contain_text("ustalone")
        s.krok("II-karta-po-czesci-I")
        page.locator(".ramka.nastepny").get_by_role("button", name="Zakończ ocenę").click()
    # #72: z zapisaną częścią I „Zakończ ocenę” otwiera od razu rozmowę, nie edycję kryteriów.
    expect(rozmowa).to_be_visible()
    expect(page.get_by_text(KROK_2)).to_have_count(0)

    # Rozmowa oceniająca (§ 10): tematy i wskaźniki jednym przebiegiem, wybór zachowania przy każdym wskaźniku.
    nr_wsk = nr_tematu = 0
    while not page.get_by_role("heading", name="Podsumowanie i punkty").is_visible():
        if page.locator(".oc-kafle").count():
            nr_wsk += 1
            kafle = page.locator(".oc-kafle .oc-kafel")
            oczekiwany = page.locator(".oc-kafle .oc-kafel:has(.znacznik)")
            # Pierwszy wskaźnik: zachowanie powyżej oczekiwań i przykład; pozostałe: oczekiwane.
            cel = kafle.nth(int(oczekiwany.evaluate("e => [...e.parentNode.children].indexOf(e)")) + 1) if nr_wsk == 1 else oczekiwany
            cel.click()
            expect(cel).to_have_attribute("aria-checked", "true")
            if nr_wsk == 1:
                page.get_by_label("Przykład z okresu (opcjonalnie)").fill(PRZYKLAD)
                page.locator(".oc-ekran .oc-tytul").click()
                page.wait_for_load_state("networkidle")
                s.krok("II-wskaznik-1")
        else:
            # Tematy rozmowy bez wskaźników: cele (jeśli wyznaczono) i rozwój; zadania z OSP są przy wskaźnikach.
            nr_tematu += 1
            if page.get_by_label("Mocne strony").count():
                page.get_by_label("Kierunki rozwoju i potrzeby (opcjonalnie)").fill("Szkolenie z prawa UE w 2027 r.")
                s.krok("II-temat-rozwoj")
        # Czekamy na zmianę licznika „N z M”, żeby nie kliknąć dwa razy w ten sam ekran.
        przed = page.locator(".oc-ekran .oc-tytul").first.inner_text()
        page.locator(".oc-nawigacja > button:not(.link)").click()
        expect(page.locator(".oc-ekran .oc-tytul", has_text=re.compile(f"^{re.escape(przed)}$"))).to_have_count(0)
    s.krok("II-podsumowanie-przed-punktami")

    # Podsumowanie (§ 11): punkty po rozmowie; pierwsze kryterium wg sugestii, drugie inaczej z uzasadnieniem.
    kryteria = page.locator(".oc-kryterium")
    if dodatkowe:
        assert kryteria.count() >= 6, f"Oczekiwano 5 obowiązkowych + 1 dodatkowego kryterium, jest {kryteria.count()}"
        expect(kryteria.filter(has_text=dodatkowe)).to_have_count(1)
    for i in range(kryteria.count()):
        kr = kryteria.nth(i)
        sugestia = kr.locator(".oc-punkt:has(.znacznik)")
        if sugestia.count() != 1:
            # Remis albo za mało danych (proces z test_samoocena w pełnym zestawie): wybór przełożonego.
            cel = sugestia.first if sugestia.count() else kr.locator(".oc-punkt").nth(2)
            cel.click()
            expect(cel).to_have_attribute("aria-checked", "true")
            pole = kr.get_by_label(re.compile("Dlaczego inaczej niż sugestia|uzasadni", re.I))
            if pole.count():
                pole.first.fill(UZASADNIENIE)
                kr.locator("h3").click()
                page.wait_for_load_state("networkidle")
            continue
        if i == 1:
            nr = int(sugestia.evaluate("e => [...e.parentNode.children].indexOf(e)"))
            punkty = kr.locator(".oc-punkt")
            cel = punkty.nth(nr + 1 if nr + 1 < punkty.count() else nr - 1)
        else:
            cel = sugestia
        cel.click()
        expect(cel).to_have_attribute("aria-checked", "true")
        if i == 1:
            kr.get_by_label(re.compile("Dlaczego inaczej niż sugestia")).fill(UZASADNIENIE)
            kr.locator("h3").click()
            page.wait_for_load_state("networkidle")
    expect(page.get_by_text("Wszystkie kryteria mają punkty.")).to_be_visible()
    s.krok("II-podsumowanie-punkty")
    dzis = date.today().isoformat()
    expect(page.get_by_label("Data rozmowy oceniającej")).to_have_value(dzis)
    page.get_by_role("button", name="Zakończ rozmowę").click()

    # Część 3 z 3 · Ocena na piśmie: wynik § 11 i arkusz na jednym ekranie, dane z wcześniejszych kroków.
    expect(page.get_by_text("Część 3 z 3 · Ocena na piśmie", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", level=1, name="Zakończenie oceny")).to_be_visible()
    expect(page.get_by_label("Miejscowość", exact=True)).to_have_value("Warszawa")
    expect(page.get_by_role("heading", name="Ocena pozytywna", exact=True)).to_be_visible()
    s.krok("II-ocena-na-pismie")
    # Braki jak użytkownik: pozycja z „Co jeszcze trzeba” rozwija sekcję i ustawia fokus w polu.
    co_trzeba = page.locator("section:has(h2:has-text('Co jeszcze trzeba'))")
    for brak, wartosc in (("Wnioski do indywidualnego programu rozwoju zawodowego", IPRZ), ("poziom poprzedniej oceny", "na poziomie oczekiwań")):
        pozycja = co_trzeba.get_by_role("button", name=re.compile(brak))
        if pozycja.count():
            pozycja.click()
            page.locator(":focus").fill(wartosc)
    expect(page.locator(".oc-nawigacja")).not_to_contain_text("Brakuje")
    page.get_by_role("button", name="Zatwierdź arkusz").click()
    expect(page.get_by_text("Arkusz zatwierdzony.")).to_be_visible(timeout=30_000)
    expect(page.get_by_text(
        "Po podpisie ocenianego wpisz datę zapoznania i zakończ ocenę."
    )).to_be_visible()
    expect(page.get_by_role("button", name="Drukuj do podpisu")).to_be_enabled()
    s.pdf("Pobierz PDF")
    page.get_by_role("button", name="Zarejestruj w EZD (próbnie)").click()
    expect(page.get_by_text(re.compile(r"^Próbna rejestracja w EZD"))).to_be_visible()
    s.krok("II-arkusz-zatwierdzony-ezd")

    # Zakończenie (§ 12 ust. 1): dzień zapoznania ocenianego z oceną, potem proces ZAKONCZONY i ocena w kartotece.
    page.get_by_label("Data zapoznania ocenianego z oceną").fill(dzis)
    page.get_by_role("button", name="Zakończ ocenę").click()
    expect(page.get_by_text(re.compile(r"^Ocena zakończona: zapoznanie z oceną"))).to_be_visible()
    expect(page.get_by_text("Arkusz włącza się do akt osobowych, kopię doręcza się ocenianemu (§ 12 ust. 2).")).to_be_visible()
    expect(page.get_by_role("button", name="Zarejestruj w EZD (próbnie)")).to_have_count(0)
    s.pdf("Pobierz arkusz (PDF)")
    s.krok("II-ocena-zakonczona")

    # Karta po zakończeniu: następny okres („Rozpocznij ocenę”), nowa ocena w „Poprzednich ocenach”.
    _karta(page, "Zielińska")
    expect(page.locator(".ramka.nastepny").get_by_role("button")).to_have_text("Rozpocznij ocenę")
    poprzednie = page.locator(".poprzednie")
    expect(poprzednie).to_contain_text("pozytywna")
    expect(poprzednie).to_contain_text(f"sporządzona {date.today().strftime('%d.%m.%Y')}")
    s.krok("II-karta-po-zakonczeniu")

    # Zgłoszenie 175: z poprzedniej oceny (zakończonej w aplikacji) wejście w szczegóły tego cyklu, tylko do odczytu.
    poprzednie.get_by_role("button", name="Szczegóły poprzedniej oceny").click()
    expect(page.get_by_role("heading", level=1, name="Rozmowa oceniająca")).to_be_visible()
    expect(page.locator(".oc-ekran input:not([disabled]), .oc-ekran textarea:not([disabled])")).to_have_count(0)
    s.krok("II-szczegoly-poprzedniej")
    s.zamknij()
