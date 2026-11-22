"""Próba jury asystenta formalnego (#53) na zestawie konfiguracja/pytania-jury.yaml.

    cd kompas-mc/backend && uv run pytest tests/test_asystent_proba_jury.py -s

`pytania`  – 30 pytań z audytu 21.11.2026 (przed poprawkami: 5/30 we właściwej pozycji FAQ).
`odlozone` – 15 pytań napisanych przed dopisaniem pozycji; tylko pomiar uogólniania.
Pytanie jest trafione, gdy odpowiedź pochodzi z pozycji FAQ wskazanej w polu `faq`: wtedy
użytkownik widzi odpowiedź napisaną przez człowieka i jej cytat. Pytania z polem `czeka_na`
mają pozycję na innej gałęzi i do jej scalenia nie liczą się do progu.
"""

from __future__ import annotations

import re

import pytest
import yaml
from kompas_core.llm import DziennikPamiec, Ekstrakcyjny

from kompas_mc.asystent import Asystent, KonfiguracjaAsystenta
from kompas_mc.ustawienia import KATALOG_MC

KONF = KATALOG_MC / "konfiguracja"
JURY = yaml.safe_load((KONF / "pytania-jury.yaml").read_text(encoding="utf-8"))
FAQ = yaml.safe_load((KONF / "faq.yaml").read_text(encoding="utf-8"))["pozycje"]
PYTANIA, ODLOZONE = JURY["pytania"], JURY["odlozone"]

# Wynik po scaleniu 53-asystent-jury (FAQ-O22, FAQ-P17; 22.11.2026): 30/30.
# Test pilnuje, żeby późniejsze zmiany go nie obniżyły.
MIN_PROBA = 30
# Zestaw odłożony przy tym samym stanie: 10/14 (przed poprawkami 1/15). Próg z zapasem
# jednego pytania, bo na tym zestawie niczego nie stroimy.
MIN_ODLOZONE = 9


def _n(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


@pytest.fixture(scope="module")
def asystent(korpus_mc, ustawienia) -> Asystent:
    return Asystent(
        korpus_mc,
        KonfiguracjaAsystenta.z_pliku(ustawienia.konfiguracja_asystenta),
        DziennikPamiec(),
        dostawcy=[Ekstrakcyjny(k=3)],
    )


def _pomiar(asystent: Asystent, zestaw: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """(trafione, chybione, czekające) – identyfikatory pytań."""
    istniejace = {p["id"] for p in FAQ}
    trafione, chybione, czekajace = [], [], []
    for q in zestaw:
        sciezka = None if q["sciezka"] == "wspolne" else q["sciezka"]
        odp = asystent.odpowiedz(q["pytanie"], sciezka)
        if odp.faq_id in q["faq"]:
            trafione.append(q["id"])
        elif q.get("czeka_na") and not istniejace & set(q["faq"]):
            czekajace.append(q["id"])
        else:
            chybione.append(f"{q['id']}→{odp.faq_id or ('cytaty' if odp.znaleziono else 'brak')}")
    return trafione, chybione, czekajace


def test_zestaw_ma_30_pytan_i_15_odlozonych():
    assert len(PYTANIA) == 30 and len(ODLOZONE) == 15
    assert len({q["id"] for q in PYTANIA + ODLOZONE}) == 45


def test_oczekiwane_pozycje_istnieja_albo_czekaja_na_galaz():
    istniejace = {p["id"] for p in FAQ}
    for q in PYTANIA + ODLOZONE:
        assert q.get("czeka_na") or set(q["faq"]) <= istniejace, q["id"]


def test_proba_jury_trafia_we_wlasciwa_pozycje(asystent):
    trafione, chybione, czekajace = _pomiar(asystent, PYTANIA)
    print(f"\npróba jury: {len(trafione)}/{len(PYTANIA)}; chybione: {chybione}; czekają na gałąź: {czekajace}")
    assert len(trafione) >= MIN_PROBA, chybione


def test_zestaw_odlozony_pomiar(asystent):
    trafione, chybione, czekajace = _pomiar(asystent, ODLOZONE)
    print(f"\nodłożone: {len(trafione)}/{len(ODLOZONE)}; chybione: {chybione}; czekają na gałąź: {czekajace}")
    assert len(trafione) >= MIN_ODLOZONE, chybione


def test_odpowiedz_z_proby_ma_tresc_i_cytat_pozycji(asystent):
    """Juror widzi odpowiedź napisaną przez człowieka i cytat źródła tej pozycji."""
    cytaty = {p["id"]: _n(p["adnotacje"][0]["cytat_dosłowny"]) for p in FAQ}
    for q in PYTANIA:
        sciezka = None if q["sciezka"] == "wspolne" else q["sciezka"]
        odp = asystent.odpowiedz(q["pytanie"], sciezka)
        if odp.faq_id not in q["faq"]:
            continue
        assert odp.tresc and odp.cytaty, q["id"]
        assert cytaty[odp.faq_id] in _n(re.sub(r"-\s*\n\s*", "", odp.cytaty[0].cytat)), q["id"]


def test_faq_i_slownik_nie_kopiuja_pytan_proby():
    testowe = {_n(q["pytanie"]) for q in PYTANIA + ODLOZONE}
    warianty = {_n(w) for p in FAQ for w in p["pytania"]}
    assert not warianty & testowe
    slownik = yaml.safe_load((KONF / "asystent.yaml").read_text(encoding="utf-8"))["slownik"]
    assert not {_n(k) for k in slownik} & testowe


def test_brak_sprzeciwu_od_pierwszej_oceny_jest_powiedziany_wprost(asystent):
    """Pkt 5 zadania: asystent komunikuje brak informacji zamiast cytatu nie na temat."""
    odp = asystent.odpowiedz("Czy od pierwszej oceny przysługuje odwołanie albo sprzeciw?", "pierwsza")
    assert odp.faq_id == "FAQ-P27"
    assert "nie ma przepisu o sprzeciwie od pierwszej oceny" in odp.tresc


def test_komunikat_o_nieznanych_slowach_zgadza_liczbe(asystent):
    jedno = asystent.odpowiedz("Ile wynosi dodatek stażowy?")
    assert jedno.nieznane_pojecia == ["stażowy"]
    assert jedno.uwagi == ["W materiałach nie znaleziono słowa z pytania: „stażowy”."]
    wiele = asystent.odpowiedz("Pracownik zgłasza mobbing i stalking. Co robić?")
    assert len(wiele.nieznane_pojecia) > 1
    assert wiele.uwagi[0].startswith("W materiałach nie znaleziono słów z pytania: „")
