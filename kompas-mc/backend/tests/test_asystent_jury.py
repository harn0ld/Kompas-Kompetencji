"""Asystent formalny jak u jury (#53): wzorce błędów z audytu 21.11, tryb bez modelu.

Pytania pochodzą z opisu #53 (audyt 30 pytań). Nie kopiujemy ich do faq.yaml – FAQ
ma własne sformułowania, a te pytania sprawdzają dopasowanie.
"""

from __future__ import annotations

import pytest
from kompas_core.llm import DziennikPamiec, Ekstrakcyjny

from kompas_mc.asystent import Asystent, KonfiguracjaAsystenta


@pytest.fixture(scope="module")
def asystent(korpus_mc, ustawienia):
    """Tylko tryb ekstrakcyjny – tak jak u jury bez klucza DeepSeek i bez Ollamy."""
    konf = KonfiguracjaAsystenta.z_pliku(ustawienia.konfiguracja_asystenta)
    return Asystent(korpus_mc, konf, DziennikPamiec(), dostawcy=[Ekstrakcyjny(k=3)])


def _cytaty(odp) -> str:
    return " ".join(c.cytat for c in odp.cytaty)


def test_kto_podlega_pierwszej_ocenie_nie_dostaje_listy_kryteriow(asystent):
    """Wzorzec 1: pewna odpowiedź z FAQ na inne pytanie („kto” ≠ „co”)."""
    odp = asystent.odpowiedz("Kto podlega pierwszej ocenie?", "pierwsza")
    assert odp.znaleziono and odp.faq_id != "FAQ-P08"
    assert "obligatoryjnie podlega osoba" in _cytaty(odp)


def test_co_podlega_ocenie_dalej_dostaje_kryteria(asystent):
    odp = asystent.odpowiedz("Co podlega ocenie przy pierwszej ocenie?", "pierwsza")
    assert odp.faq_id == "FAQ-P08"


@pytest.mark.parametrize(
    ("pytanie", "sciezka", "fraza"),
    [
        # Wzorzec 2: potoczne słowa nie blokują odpowiedzi.
        ("Kiedy najwcześniej można sporządzić ocenę okresową?", "okresowa", "nie wcześniej niż"),
        ("Kiedy najwcześniej można dokonać pierwszej oceny?", "pierwsza", "nie wcześniej niż"),
        ("Kiedy najpóźniej trzeba dokonać pierwszej oceny?", "pierwsza", "nie później niż"),
        ("Co grozi urzędnikowi za drugą negatywną ocenę okresową?", "okresowa", "rozwiązanie stosunku pracy"),
        ("Jakie są konsekwencje negatywnej oceny okresowej?", "okresowa", "rozwiązanie stosunku pracy"),
    ],
)
def test_potoczne_slowa_nie_blokuja(asystent, pytanie, sciezka, fraza):
    odp = asystent.odpowiedz(pytanie, sciezka)
    assert odp.znaleziono, (pytanie, odp.nieznane_pojecia)
    assert not odp.nieznane_pojecia
    assert fraza in _cytaty(odp).replace("\n", " ")


@pytest.mark.parametrize("sciezka", ["okresowa", None])
def test_przyklad_z_czatu_kroku_6(asystent, sciezka):
    """Wzorzec 3: przykład z pola czatu w kroku 6 dostaje odpowiedź o informacji zwrotnej."""
    odp = asystent.odpowiedz("Jak przekazać ocenę 3 za współpracę?", sciezka)
    assert odp.znaleziono
    assert "informacj" in _cytaty(odp) and "zwrotn" in _cytaty(odp)


def test_poza_baza_dalej_odmowa(asystent):
    """Słownik potocznych słów nie otwiera pytań spoza bazy."""
    for q in ("Co grozi za spóźnienie do pracy?", "Ile wynosi dodatek stażowy?"):
        assert not asystent.odpowiedz(q, "okresowa").znaleziono, q
