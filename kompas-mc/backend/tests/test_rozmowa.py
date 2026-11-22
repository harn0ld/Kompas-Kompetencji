"""Asystent rozmowy (#35, krok 6): plan rozmowy jako sugestia, z powiązaniem i uzasadnieniem."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from kompas_core.llm import Cytat, Odpowiedz, Tryb
from kompas_core.zrodla.cli import main as waliduj

from kompas_mc.app import utworz_aplikacje
from kompas_mc.ustawienia import KATALOG_MC
from test_ocena import _proces_z_krokiem2


@pytest.fixture(scope="module")
def klient(ustawienia, tmp_path_factory):
    """Własna baza: inne testy zostawiają procesy w toku (jedna osoba = jeden proces)."""
    dane = tmp_path_factory.mktemp("rozmowa")
    ust = replace(ustawienia, baza=dane / "rozmowa.db", log_llm=dane / "llm.jsonl")
    with TestClient(utworz_aplikacje(ust)) as k:
        yield k


@pytest.fixture(scope="module")
def naglowek(klient):
    def zaloguj(login: str) -> dict:
        r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj

PRZYKLAD = {
    "sytuacja": "Pilna opinia do projektu rozporządzenia",
    "dzialanie": "Przygotowała analizę z wariantami",
    "rezultat": "Stanowisko przyjęte bez poprawek",
    "powtarzalnosc": "REGULARNE",
    "zlozonosc": "WYSOKA",
}


def _proces(klient, naglowek, osoba_id, sciezka, login="przelozony1"):
    h = naglowek(login)
    proces = next(
        (p for p in klient.get("/api/procesy", headers=h).json()
         if p["osoba_id"] == osoba_id and p["sciezka"] == sciezka and p["status"] == "W_TOKU"),
        None,
    )
    if proces is None:
        r = klient.post("/api/procesy", json={"osoba_id": osoba_id, "sciezka": sciezka}, headers=h)
        assert r.status_code == 201, r.text
        proces = r.json()
    if proces["krok2"] is None:
        p = klient.get(f"/api/procesy/{proces['id']}/krok2", headers=h).json()
        wsk = {
            k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"][:2]]
            for k in p["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"
        }
        r = klient.put(f"/api/procesy/{proces['id']}/krok2", json={"wskazniki": wsk}, headers=h)
        assert r.status_code == 200, r.text
        proces = r.json()
    return proces


def _okresowa_z_ocenami(klient, naglowek):
    """P-104 (radca, arkusz C): kryterium 0 – mocna strona i brak podstaw; kryterium 1 –
    sugestia 5, decyzja 1 (odchylenie o 2 poziomy i „znacznie poniżej”); kryterium 2 – poziom 3."""
    h = naglowek("przelozony1")
    proces = _proces(klient, naglowek, "P-104", "okresowa")
    url = f"/api/procesy/{proces['id']}/ocena"
    stan = klient.get(url, headers=h).json()
    k0, k1, k2 = stan["kryteria"][:3]
    (a, b), (c, d), (e, f) = ([w["wskaznik_id"] for w in k["wskazniki"][:2]] for k in (k0, k1, k2))
    r = klient.put(f"{url}/wskazniki", headers=h, json={"wskazniki": {
        a: {"poziom": 9, "przyklady": [PRZYKLAD]},
        b: {"brak_podstaw": True},
        c: {"poziom": 5, "przyklady": [PRZYKLAD]},
        d: {"poziom": 5, "przyklady": [PRZYKLAD]},
        e: {"poziom": 3, "przyklady": [PRZYKLAD]},
        f: {"poziom": 3, "przyklady": [PRZYKLAD]},
    }})
    assert r.status_code == 200, r.text
    r = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": {
        k1["kompetencja_id"]: {"punkty": 1, "uzasadnienie": "Test odchylenia od sugestii."},
    }})
    assert r.status_code == 200, r.text
    return proces, r.json(), (k0, k1, k2), (a, b, e)


def test_plan_rozmowy_okresowej(klient, naglowek, korpus_mc):
    h = naglowek("przelozony1")
    proces, stan_przed, (k0, k1, k2), (mocny, brak, slaby) = _okresowa_z_ocenami(klient, naglowek)
    r = klient.post(f"/api/procesy/{proces['id']}/rozmowa", headers=h, json={})
    assert r.status_code == 200, r.text
    plan = r.json()

    # wszystko jest sugestią, bez modelu językowego
    assert plan["status"].startswith("SUGESTIA") and plan["tryb"] == "SZABLONY"
    assert "do edycji" in plan["oznaczenie"]

    # zakres z § 10 rozp. 2016; bez celów nie ma punktu o celach
    assert [z["id"] for z in plan["zakres"]] == ["zakres.okresowa.obowiazki", "zakres.okresowa.rozwoj"]

    # każde pytanie ma uzasadnienie, powiązanie i źródło (kryterium #35)
    assert plan["pytania"]
    for p in plan["pytania"]:
        assert p["uzasadnienie"].strip() and p["adnotacje"], p
        typ = p["powiazanie"]["typ"]
        assert typ in {"wskaznik", "przyklad", "zadanie_osp", "przepis"}
        if typ in {"wskaznik", "przyklad"}:
            assert p["powiazanie"]["wskaznik_id"]
        if typ == "zadanie_osp":
            assert p["powiazanie"]["zadanie_osp"] >= 1
    szablony = {p["szablon"] for p in plan["pytania"]}
    assert {"pyt.osp.zadanie", "pyt.wskaznik.powtarzalnosc", "pyt.wskaznik.standard", "pyt.rozwoj.okresowa"} <= szablony
    assert "Pilna opinia" in next(p["tresc"] for p in plan["pytania"] if p["szablon"] == "pyt.wskaznik.powtarzalnosc")

    # argument: zachowanie dosłownie z modelu, źródło w korpusie
    arg = next(a for a in plan["argumenty"] if a["wskaznik_id"] == mocny)
    assert arg["poziom"] == 9 and arg["rezultat"] == PRZYKLAD["rezultat"]
    zr = arg["zachowanie_zrodlo"]
    zrodlo = next(
        f for f in korpus_mc.korpus.fragmenty
        if f.doc_id == "model-kompetencji" and f.lokalizator == zr["lokalizator"]
    )
    assert zr["doc_id"] == "model-kompetencji"
    assert arg["zachowanie"] == " ".join(zrodlo.tekst.split())

    # szkic informacji zwrotnej
    nazwa = lambda k: k["wskazniki"][0]["nazwa"].rstrip(".")  # noqa: E731
    assert any(nazwa(k0) in s for s in plan["informacja_zwrotna"]["mocne_strony"])
    assert any(nazwa(k2) in s for s in plan["informacja_zwrotna"]["obszary_rozwoju"])
    assert not any(".:" in s or ".”." in s for s in sum(plan["informacja_zwrotna"].values(), []))
    tresci = [p["tresc"] for p in plan["pytania"] if p["powiazanie"]["typ"] == "przyklad"]
    assert len(tresci) == len(set(tresci))  # ten sam przykład nie powtarza pytania

    # kwestie do omówienia
    kw = {(k["id"], k.get("wskaznik_id") or k.get("kompetencja")) for k in plan["kwestie"]}
    assert ("kwestia.brak-podstaw", brak) in kw
    assert ("kwestia.odchylenie-od-sugestii", k1["nazwa"]) in kw
    assert ("kwestia.znacznie-ponizej", k1["nazwa"]) in kw
    assert all(k["adnotacje"] for k in plan["kwestie"])

    # plan nie zmienia ocen
    stan_po = klient.get(f"/api/procesy/{proces['id']}/ocena", headers=h).json()
    assert stan_po["kryteria"] == stan_przed["kryteria"]


def test_cele_dodaja_punkt_zakresu_i_pytanie(klient, naglowek):
    h = naglowek("przelozony1")
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    plan = klient.post(
        f"/api/procesy/{proces['id']}/rozmowa", headers=h, json={"cele": ["Wdrożenie rejestru opinii"]}
    ).json()
    assert "zakres.okresowa.cele" in [z["id"] for z in plan["zakres"]]
    assert any(p["szablon"] == "pyt.cele" and "rejestru opinii" in p["tresc"] for p in plan["pytania"])


def test_plan_rozmowy_pierwszej_oceny(klient, naglowek):
    h = naglowek("przelozony1")
    proces = _proces(klient, naglowek, "P-203", "pierwsza")
    url = f"/api/procesy/{proces['id']}/ocena"
    stan = klient.get(url, headers=h).json()
    w = {k["kompetencja_id"]: [x["wskaznik_id"] for x in k["wskazniki"]] for k in stan["kryteria"]}
    klient.put(f"{url}/wskazniki", headers=h, json={"wskazniki": {
        i: {"poziom": 3, "przyklady": [PRZYKLAD]} for ids in list(w.values())[:2] for i in ids
    }})
    kryt = [k["kompetencja_id"] for k in stan["kryteria"][:2]]
    r = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": {
        k: {"punkty": 3, "uzasadnienie": "Test."} for k in kryt
    }})
    assert r.status_code == 200, r.text

    plan = klient.post(f"/api/procesy/{proces['id']}/rozmowa", headers=h, json={
        "sprawozdanie_zlozone_w_terminie": False,
        "egzamin_obowiazkowy": False,
        "fragment_sprawozdania": "Opracowanie analizy barier prawnych",
    }).json()
    zakres = [z["id"] for z in plan["zakres"]]
    assert "zakres.pierwsza.sprawozdanie" in zakres and "zakres.pierwsza.egzamin" not in zakres
    szablony = {p["szablon"] for p in plan["pytania"]}
    assert "pyt.sprawozdanie" in szablony and "pyt.rozwoj.pierwsza" in szablony
    assert "pyt.osp.zadanie" not in szablony and "pyt.cele" not in szablony
    ids = {k["id"] for k in plan["kwestie"]}
    assert {"kwestia.sprawozdanie-niezlozone", "kwestia.dwie-oceny-3pkt"} <= ids
    assert "kwestia.znacznie-ponizej" not in ids  # tylko ocena okresowa


def test_uprawnienia_planu(klient, naglowek):
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    url = f"/api/procesy/{proces['id']}/rozmowa"
    assert klient.post(url, json={}).status_code == 401
    assert klient.post(url, json={}, headers=naglowek("hr")).status_code == 403
    assert klient.post(url, json={}, headers=naglowek("oceniany")).status_code == 403
    assert klient.post(url, json={}, headers=naglowek("przelozony2")).status_code == 403
    assert klient.post("/api/procesy/999999/rozmowa", json={}, headers=naglowek("przelozony1")).status_code == 404


def test_czat_ma_kontekst_procesu_bez_danych_identyfikujacych(klient, naglowek):
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    zapytania = []

    class Atrapa:
        nazwa = "atrapa"
        model = "test"
        tryb = Tryb.NA_ZYWO

        def odpowiedz(self, zapytanie):
            zapytania.append(zapytanie)
            fragment = zapytanie.fragmenty[0]
            return Odpowiedz(
                cytaty=[Cytat(fragment_id=fragment.id, cytat=fragment.tekst)],
                tresc="Sugestia oparta na materiale.",
            )

    poprzedni = klient.app.state.asystent.dostawcy
    klient.app.state.asystent.dostawcy = [Atrapa()]
    try:
        r = klient.post(
            f"/api/procesy/{proces['id']}/rozmowa/czat",
            headers=naglowek("przelozony1"),
            json={"pytanie": "Kiedy ocena okresowa jest negatywna?"},
        )
    finally:
        klient.app.state.asystent.dostawcy = poprzedni

    assert r.status_code == 200, r.text
    odp = r.json()
    assert odp["tryb"] == "NA_ŻYWO" and odp["cytaty"][0]["lokalizator"]
    assert "Sugestia asystenta" in odp["oznaczenie_sugestii"]
    # Atrapa nie zwraca JSON-u z kwestiami, więc czat przygotowania (#178) oddaje pytanie dotychczasowej ścieżce.
    prompt = next(z for z in zapytania if z.operacja == "asystent_formalny").pytanie
    assert "KONTEKST PROCESU" in prompt and "wybrane_wskazniki" in prompt
    assert "P-104" not in prompt and "P-001" not in prompt
    assert "Michał" not in prompt and "Wójcik-Demo" not in prompt
    assert "Marta" not in prompt and "Kowalczyk-Demo" not in prompt
    assert "Oceniany" in prompt and "Przełożony" in prompt


def test_czat_spoza_bazy_i_uprawnienia(klient, naglowek):
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    url = f"/api/procesy/{proces['id']}/rozmowa/czat"
    body = {"pytanie": "Jak zastosować teleportację kwantową w ocenie?"}
    assert klient.post(url, json=body).status_code == 401
    assert klient.post(url, json=body, headers=naglowek("hr")).status_code == 403
    assert klient.post(url, json=body, headers=naglowek("oceniany")).status_code == 403
    r = klient.post(url, json=body, headers=naglowek("przelozony1"))
    assert r.status_code == 200
    assert r.json()["znaleziono"] is False
    assert r.json()["komunikat"] == "brak wystarczających informacji w bazie wiedzy"


def test_cytaty_konfiguracji_rozmowy_sa_w_korpusie():
    konf = KATALOG_MC / "konfiguracja"
    assert waliduj(["--manifest", str(konf / "korpus.yaml"), str(konf / "rozmowa.yaml")]) == 0


def test_dane_osobowe_nie_sa_dozwolone_dla_modelu():
    import yaml

    d = yaml.safe_load((KATALOG_MC / "konfiguracja" / "rozmowa.yaml").read_text(encoding="utf-8"))
    zakazane = set(d["dane_dla_modelu"]["zabronione"])
    assert {"imie", "nazwisko", "komorka", "osoba_id"} <= zakazane
    assert "przyklad" in d["dane_dla_modelu"]["dozwolone"]
    assert not zakazane & set(d["dane_dla_modelu"]["dozwolone"])


def test_uwagi_zamiast_przykladu_trafiaja_do_planu(klient, naglowek):
    """Pole „Przykład z okresu” zapisuje uwagi (#46): plan rozmowy używa ich zamiast „(dopisz przykład)”."""
    h = naglowek("przelozony1")
    proces = _proces(klient, naglowek, "P-105", "okresowa")
    url = f"/api/procesy/{proces['id']}"
    stan = klient.get(f"{url}/ocena", headers=h).json()
    w = stan["kryteria"][0]["wskazniki"][0]["wskaznik_id"]
    uwagi = "Przygotował opinię w dwa dni zamiast w tydzień."
    r = klient.put(f"{url}/ocena/wskazniki", headers=h, json={"wskazniki": {w: {"poziom": 9, "uwagi": uwagi}}})
    assert r.status_code == 200, r.text
    plan = klient.post(f"{url}/rozmowa", headers=h, json={}).json()
    assert any(uwagi.rstrip(".") in m for m in plan["informacja_zwrotna"]["mocne_strony"])
    assert not any("(dopisz przykład)" in m for m in plan["informacja_zwrotna"]["mocne_strony"])
    assert any(uwagi in q["tresc"] for q in plan["pytania"] if q["powiazanie"]["typ"] == "przyklad")
    arg = next(a for a in plan["argumenty"] if a["wskaznik_id"] == w)
    assert arg["przyklad"] == uwagi and arg["uwaga"] is None



def test_kazdy_nieoceniony_wskaznik_ma_swoje_pytanie(klient, naglowek):
    """Szablon pytania o przykład nie zawiera nazwy wskaźnika; mimo tej samej treści każdy wskaźnik ma pytanie."""
    h = naglowek("przelozony1")
    proces = _proces(klient, naglowek, "P-101", "okresowa")
    stan = klient.get(f"/api/procesy/{proces['id']}/ocena", headers=h).json()
    plan = klient.post(f"/api/procesy/{proces['id']}/rozmowa", headers=h, json={}).json()
    nieocenione = {w["wskaznik_id"] for k in stan["kryteria"] for w in k["wskazniki"] if w["ocena"] is None}
    z_pytaniem = {q["powiazanie"]["wskaznik_id"] for q in plan["pytania"] if q["powiazanie"]["typ"] == "wskaznik"}
    assert nieocenione and nieocenione <= z_pytaniem


class _AtrapaPodpowiedzi:
    """Dostawca LLM w teście: pytanie z cytatem z opisu wskaźnika; zapisuje, co dostał."""

    nazwa = "atrapa"
    model = "test"
    tryb = Tryb.NA_ZYWO

    def __init__(self, tresc="Kiedy w tym okresie było to widać?"):
        self.zapytania = []
        self.tresc = tresc

    def odpowiedz(self, zapytanie):
        self.zapytania.append(zapytanie)
        f = zapytanie.fragmenty[0]
        return Odpowiedz(cytaty=[Cytat(fragment_id=f.id, cytat=f.tekst[:40])], tresc=self.tresc)


def test_podpowiedz_ai_przy_wskazniku_bez_danych_osobowych(klient, naglowek):
    """Karol 22.11: podpowiedź przy wskaźniku z modelu (Scaleway); kontekst bez imion, 404 dla obcego wskaźnika."""
    h = naglowek("przelozony2")
    proces = _proces_z_krokiem2(klient, naglowek, "P-103", "okresowa", "przelozony2")
    wid = proces["krok2"]["kryteria"][0]["wskazniki"][0]["id"]
    llm = klient.app.state.cele_llm
    atrapa, poprzedni = _AtrapaPodpowiedzi(), llm.dostawcy
    llm.dostawcy = [atrapa]
    try:
        url = f"/api/procesy/{proces['id']}/rozmowa/podpowiedz"
        r = klient.post(url, json={"wskaznik_id": wid}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["pytanie"] == "Kiedy w tym okresie było to widać?" and r.json()["dostawca"] == "atrapa"
        pracownik = klient.get("/api/pracownicy/P-103", headers=h).json()
        tekst = atrapa.zapytania[0].pytanie
        assert pracownik["nazwisko"] not in tekst and pracownik["imie"] not in tekst
        assert klient.post(url, json={"wskaznik_id": "nie-ma"}, headers=h).status_code == 404
        # Model nie podsuwa oceny ani punktów: taka odpowiedź nie trafia na ekran (zostaje szablon).
        llm.dostawcy = [_AtrapaPodpowiedzi("Proponuję 7 pkt, bo przykład jest mocny.")]
        assert klient.post(url, json={"wskaznik_id": wid}, headers=h).json()["pytanie"] is None
        llm.dostawcy = []
        assert klient.post(url, json={"wskaznik_id": wid}, headers=h).json()["pytanie"] is None
        assert klient.post(url, json={"wskaznik_id": wid}, headers=naglowek("hr")).status_code == 403
    finally:
        llm.dostawcy = poprzedni


@pytest.mark.parametrize(
    "tekst,ocena",
    [
        ("Proponuję 3 pkt za to kryterium.", True),
        ("Sugeruję ocenić to na poziomie oczekiwań.", True),
        ("To poziom 7.", True),
        ("Powinien otrzymać ocenę powyżej oczekiwań.", True),
        ("Jak wyglądała realizacja tego zadania w okresie oceny?", False),
        ("Standard to poziom „na poziomie oczekiwań”: jak to wyglądało u Ciebie?", False),
        ("W razie oceny negatywnej przysługuje sprzeciw w 7 dni.", False),
        # Przykłady icc-8a (22.11): odwołania do przepisów przechodzą, propozycje oceny nie.
        ("Zgodnie z § 10 ust. 1 pkt 2 rozporządzenia omawia się cele.", False),
        ("Art. 81 ust. 1 pkt 3 ustawy dotyczy oceny.", False),
        ("Zakres rozmowy opisuje § 3 pkt 1 poradnika.", False),
        ("Sugeruję ocenę negatywną.", True),
        ("Proponuję wynik pozytywny oceny okresowej.", True),
        ("Oceniany zasługuje na poziom powyżej oczekiwań.", True),
        ("Ocena: 7.", True),
        ("Moim zdaniem siedem punktów będzie właściwe.", True),
        ("Warto dać mu 7.", True),
    ],
)
def test_tekst_modelu_nie_podsuwa_oceny(tekst, ocena):
    """icc-8a 22.11: core sprawdza tylko cytaty; propozycja punktów albo poziomu nie może trafić na ekran."""
    from kompas_mc.asystent import proponuje_ocene

    assert proponuje_ocene(tekst) is ocena


@pytest.mark.parametrize(
    "tresc,pytanie,powod",
    [
        ('{"pytanie": "Kiedy w tym okresie było to widać?"}', "Kiedy w tym okresie było to widać?", None),
        ("„Jak to wyglądało przy opiniach prawnych?”", "Jak to wyglądało przy opiniach prawnych?", None),
        ("Dobiera i stosuje wiedzę merytoryczną odpowiednią do zadania.", None, "nie jest pytaniem"),
        ('{"pytanie": "Proponuję 7 pkt?"}', None, "podsuwa ocenę"),
        (None, None, "brak treści"),
    ],
)
def test_pytanie_z_tresci_modelu(tresc, pytanie, powod):
    """#164: core każe składać tresc z cytatów; pytanie przychodzi w JSON, cytat bez pytania odpada."""
    from kompas_mc.rozmowa_api import pytanie_z_tresci

    assert pytanie_z_tresci(tresc) == (pytanie, powod)


def test_czat_przyklad_z_pola_odpowiada_bez_modelu(klient, naglowek, monkeypatch):
    """#53: przykład z pola czatu („Jak przekazać ocenę 3 za współpracę?”) dostaje odpowiedź
    w trybie ekstrakcyjnym – tak jak u jury bez klucza DeepSeek i bez Ollamy."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    r = klient.post(
        f"/api/procesy/{proces['id']}/rozmowa/czat",
        headers=naglowek("przelozony1"),
        json={"pytanie": "Jak przekazać ocenę 3 za współpracę?"},
    )
    assert r.status_code == 200, r.text
    odp = r.json()
    assert odp["znaleziono"] is True, odp
    assert any("informacji zwrotnej" in c["cytat"] for c in odp["cytaty"])


def _czat_z_atrapa(klient, naglowek, tresc_modelu):
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    zapytania = []

    class Atrapa:
        nazwa, model, tryb = "atrapa", "test", Tryb.NA_ZYWO

        def odpowiedz(self, zapytanie):
            zapytania.append(zapytanie)
            ocena = [f for f in zapytanie.fragmenty if f.id.startswith("ocena#")]
            f = ocena[0] if ocena else zapytanie.fragmenty[0]
            tresc = tresc_modelu if ocena else "Odpowiedź ze źródeł."
            return Odpowiedz(cytaty=[Cytat(fragment_id=f.id, cytat=f.tekst[:60])], tresc=tresc)

    poprzedni = klient.app.state.asystent.dostawcy
    klient.app.state.asystent.dostawcy = [Atrapa()]
    try:
        r = klient.post(f"/api/procesy/{proces['id']}/rozmowa/czat", headers=naglowek("przelozony1"),
                        json={"pytanie": "Jakie kwestie omówić i jakie argumenty uzasadniają ocenę komunikacji?"})
    finally:
        klient.app.state.asystent.dostawcy = poprzedni
    assert r.status_code == 200, r.text
    return r.json(), zapytania


def test_czat_przygotowania_kwestie_i_argumenty_z_danych_oceny(klient, naglowek):
    """#178: na pytanie o tę osobę model cytuje dane oceny (ocena#…) i odpowiada kwestiami i argumentami."""
    tresc = {"kwestie": ["Dopytać o przykład współpracy z innymi komórkami."],
             "argumenty": ["Przykład z okresu: uzgodnienie stanowiska z trzema wydziałami w terminie."]}
    odp, zapytania = _czat_z_atrapa(klient, naglowek, tresc)
    assert odp["kwestie"] == tresc["kwestie"] and odp["argumenty"] == tresc["argumenty"]
    assert odp["tryb"] == "NA_ŻYWO" and odp["cytaty"][0]["dokument"] == "Bieżąca ocena (dane z aplikacji)"
    z = next(z for z in zapytania if z.operacja == "asystent_przygotowanie")
    oceny = [f for f in z.fragmenty if f.id.startswith("ocena#")]
    assert oceny and any(not f.id.startswith("ocena#") for f in z.fragmenty), "dane oceny obok przepisów"
    tekst = z.pytanie + " ".join(f.tekst for f in oceny)
    for zakazane in ("P-104", "Michał", "Wójcik-Demo", "Marta", "Kowalczyk-Demo"):
        assert zakazane not in tekst, zakazane
    assert not any("punkt" in f.tekst for f in oceny), "dane oceny bez punktów"


def test_czat_przygotowania_nie_podsuwa_oceny(klient, naglowek):
    """Tekst modelu z propozycją punktów nie trafia do przełożonego: zostaje dotychczasowa ścieżka czatu."""
    tresc = {"kwestie": ["Pracownik zasługuje na 7 punktów za komunikację."], "argumenty": []}
    odp, zapytania = _czat_z_atrapa(klient, naglowek, tresc)
    assert odp["kwestie"] == [] and odp["argumenty"] == []
    assert any(z.operacja == "asystent_formalny" for z in zapytania)


def test_przygotowanie_ma_dluzszy_limit_czasu_niz_asystent():
    """Zgłoszenie 181: ogólne pytanie z danymi wszystkich wskaźników potrafi przekroczyć 30 s; przygotowanie
    dostaje 60 s na kopii dostawcy, a dostawca asystenta formalnego zostaje bez zmian."""
    from kompas_core.llm import OpenAiZgodny

    from kompas_mc.rozmowa_api import LIMIT_PRZYGOTOWANIA_S, _z_limitem

    d = OpenAiZgodny(base_url="https://example.invalid/v1", model="m", zmienna_klucza="X", timeout=30)
    k = _z_limitem(d)
    assert k.timeout == LIMIT_PRZYGOTOWANIA_S == 60 and d.timeout == 30


def test_przygotowanie_ponawia_raz_po_odrzuceniu(klient, naglowek):
    """Zgłoszenie 183: pierwsza odpowiedź modelu odrzucona przez walidator (liczba spoza cytatów) → druga próba
    tym samym modelem, zanim czat wróci do dotychczasowej ścieżki."""
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    proby = []

    class Atrapa:
        nazwa, model, tryb = "atrapa", "test", Tryb.NA_ZYWO

        def odpowiedz(self, zapytanie):
            proby.append(zapytanie.operacja)
            f = next(f for f in zapytanie.fragmenty if f.id.startswith("ocena#"))
            punkt = "Dopytać o przykład z 28 sytuacji." if len(proby) == 1 else "Dopytać o przykład współpracy."
            return Odpowiedz(cytaty=[Cytat(fragment_id=f.id, cytat=f.tekst[:60])],
                             tresc={"kwestie": [punkt], "argumenty": []})

    poprzedni = klient.app.state.asystent.dostawcy
    klient.app.state.asystent.dostawcy = [Atrapa()]
    try:
        r = klient.post(f"/api/procesy/{proces['id']}/rozmowa/czat", headers=naglowek("przelozony1"),
                        json={"pytanie": "Na co zwrócić uwagę w rozmowie z tą osobą?"})
    finally:
        klient.app.state.asystent.dostawcy = poprzedni
    assert r.status_code == 200, r.text
    assert r.json()["kwestie"] == ["Dopytać o przykład współpracy."]
    assert proby == ["asystent_przygotowanie", "asystent_przygotowanie"]


@pytest.mark.parametrize("pytanie, poczatek", [
    ("hej", "Cześć!"), ("Dzień dobry!", "Cześć!"), ("cześć :)", "Cześć!"), ("Dzięki", "Proszę bardzo"),
])
def test_czat_odpowiada_na_powitanie_bez_odmowy(klient, naglowek, pytanie, poczatek):
    """Zgłoszenie 207 (Karol 22.11 09:39: „a co jak napiszę do asystenta hej?”): powitanie to nie pytanie do bazy."""
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    r = klient.post(f"/api/procesy/{proces['id']}/rozmowa/czat", headers=naglowek("przelozony1"), json={"pytanie": pytanie})
    odp = r.json()
    assert r.status_code == 200 and odp["znaleziono"] is True and odp["tresc"].startswith(poczatek), odp
    assert odp["cytaty"] == [] and not odp.get("nieznane_pojecia")


def test_powitanie_z_pytaniem_to_zwykle_pytanie():
    from kompas_mc.rozmowa_api import grzecznosc

    assert grzecznosc("hej, jakie kwestie omówić na rozmowie?") is None
    assert grzecznosc("Jakie argumenty uzasadniają ocenę?") is None
