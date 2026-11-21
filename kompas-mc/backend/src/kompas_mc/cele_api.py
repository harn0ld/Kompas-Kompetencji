"""API celów rozwojowych (#10): lista, propozycja, edycja, akceptacja, odrzucenie, status, podpowiedzi.

Uprawnienia (``role.yaml``): ``cele.czytaj`` (przełożony, oceniany, HR – tylko odczyt),
``cele.proponuj`` (przełożony, oceniany), ``cele.zatwierdz`` (przełożony). Reguły dostępu do
zasobu ``pracownik`` zawężają je jak wszędzie: przełożony podwładnych, oceniany siebie.
Konfiguracja: ``app.state.cele`` (``konfiguracja/cele.yaml``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik

from .cele import (
    BladCelu,
    Cel,
    Odrzucenie,
    PodpowiedzCelu,
    PodpowiedziCelow,
    Strona,
    TrescCelu,
    WpisHistorii,
    ZmianaStatusu,
    do_dziennika,
    edytuj,
    lista,
    utworz,
    wczytaj,
    zmien_status,
)
from .krok2_api import StanKroku2
from .ocena import zbuduj_stan
from .ocena_api import _wczytaj_dane
from .procesy import wczytaj_proces
from .qnt import MockQnt
from .rozwoj import DaneRozwoju, OcenaWskaznika, zaproponuj

ZRODLO_PODPOWIEDZI_OD_KROKU = 6
"""Podpowiedzi biorą wskaźniki z ostatniej oceny sporządzonej na piśmie (krok ≥ 6), nie z oceny w toku:
pracownik nie może zobaczyć ocen przełożonego, zanim ten je wystawi."""


def router(auth: Autoryzacja, qnt: MockQnt, stan2: StanKroku2) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["cele rozwojowe"])

    def osoba(osoba_id: str, uz: Uzytkownik, akcja: str) -> dict:
        p = qnt.pracownik(osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", p.model_dump(), akcja)
        return p.model_dump()

    def strona(uz: Uzytkownik, rekord: dict) -> Strona:
        if auth.moze(uz, "pracownik", rekord, "cele.zatwierdz"):
            return "przelozony"
        if auth.moze(uz, "pracownik", rekord, "cele.proponuj"):
            return "pracownik"
        raise HTTPException(403, "Brak dostępu do celów tej osoby")

    def cel_z_osoba(request: Request, cel_id: int, uz: Uzytkownik, akcja: str) -> tuple[Cel, dict]:
        cel = wczytaj(request.app.state.baza, cel_id)
        if cel is None:
            raise HTTPException(404, "Nie ma takiego celu")
        return cel, osoba(cel.osoba_id, uz, akcja)

    def sprawdz_tresc(request: Request, tresc: TrescCelu, kto: Strona) -> None:
        if kto == "pracownik" and not request.app.state.cele.pracownik_moze_edytowac:
            raise HTTPException(403, "Cele tworzy i zmienia przełożony.")
        if tresc.wskaznik_id and tresc.wskaznik_id not in {w.id for k in stan2.model.kompetencje for w in k.wskazniki}:
            raise HTTPException(422, f"Nie ma wskaźnika „{tresc.wskaznik_id}” w modelu kompetencji.")

    def z_historia(request: Request, cel_id: int) -> Cel:
        cel = wczytaj(request.app.state.baza, cel_id)
        dziennik: Dziennik = request.app.state.dziennik
        cel.historia = [
            WpisHistorii(czas=w.czas, autor=w.autor, zmiany=w.roznica) for w in dziennik.historia("cel", str(cel_id))
        ]
        return cel

    def zapisz_zmiane(request: Request, uz: Uzytkownik, cel_id: int, przed: dict) -> Cel:
        po = wczytaj(request.app.state.baza, cel_id)
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(uz.login, "cel", str(cel_id), przed, do_dziennika(po), request.app.state.cele.regula.id)
        return z_historia(request, cel_id)

    def wykonaj(request: Request, uz: Uzytkownik, cel: Cel, zmiana) -> Cel:
        przed = do_dziennika(cel)
        try:
            zmiana()
        except BladCelu as e:
            raise HTTPException(e.kod, e.komunikat) from e
        return zapisz_zmiane(request, uz, cel.id, przed)

    @r.get("/cele/ustawienia")
    def ustawienia(request: Request, uz: Uzytkownik = auth.wymagaj("cele.czytaj")) -> dict[str, bool]:
        """Czy pracownik tworzy i zmienia cele sam (``pracownik_moze_edytowac``); interfejs ukrywa wtedy formularz."""
        return {"pracownik_moze_edytowac": request.app.state.cele.pracownik_moze_edytowac}

    @r.get("/pracownicy/{osoba_id}/cele")
    def cele_osoby(osoba_id: str, request: Request, uz: Uzytkownik = auth.wymagaj("cele.czytaj")) -> list[Cel]:
        """Cele osoby z historią zmian. HR widzi je tylko do odczytu."""
        osoba(osoba_id, uz, "cele.czytaj")
        return [z_historia(request, c.id) for c in lista(request.app.state.baza, osoba_id)]

    @r.post("/pracownicy/{osoba_id}/cele", status_code=201)
    def nowy(osoba_id: str, body: TrescCelu, request: Request, uz: Uzytkownik = auth.wymagaj("cele.proponuj")) -> Cel:
        """Przełożony tworzy cel od razu zatwierdzony; pracownik (gdy wolno) tworzy propozycję."""
        rekord = osoba(osoba_id, uz, "cele.proponuj")
        kto = strona(uz, rekord)
        sprawdz_tresc(request, body, kto)
        cel_id = utworz(request.app.state.baza, osoba_id, body, kto, uz.login, datetime.now(UTC))
        return zapisz_zmiane(request, uz, cel_id, {})

    @r.put("/cele/{cel_id}")
    def zmien(cel_id: int, body: TrescCelu, request: Request, uz: Uzytkownik = auth.wymagaj("cele.proponuj")) -> Cel:
        """Zmiana treści. Zmiana pracownika przywraca „propozycja”; osiągniętego i porzuconego nie zmienia nikt."""
        cel, rekord = cel_z_osoba(request, cel_id, uz, "cele.proponuj")
        kto = strona(uz, rekord)
        sprawdz_tresc(request, body, kto)
        return wykonaj(request, uz, cel, lambda: edytuj(request.app.state.baza, cel, body, kto, datetime.now(UTC)))

    @r.post("/cele/{cel_id}/zatwierdz")
    def zatwierdz(cel_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("cele.zatwierdz")) -> Cel:
        cel, _ = cel_z_osoba(request, cel_id, uz, "cele.zatwierdz")
        return wykonaj(request, uz, cel, lambda: zmien_status(
            request.app.state.baza, cel, "zatwierdzony", "przelozony", datetime.now(UTC)))

    @r.post("/cele/{cel_id}/odrzuc")
    def odrzuc(cel_id: int, body: Odrzucenie, request: Request, uz: Uzytkownik = auth.wymagaj("cele.zatwierdz")) -> Cel:
        """Odrzucenie propozycji wymaga komentarza; pracownik może ją poprawić (wraca „propozycja”)."""
        cel, _ = cel_z_osoba(request, cel_id, uz, "cele.zatwierdz")
        komentarz = body.komentarz.strip()
        if not komentarz:
            raise HTTPException(422, "Odrzucenie wymaga komentarza.")
        return wykonaj(request, uz, cel, lambda: zmien_status(
            request.app.state.baza, cel, "odrzucony", "przelozony", datetime.now(UTC), komentarz))

    @r.post("/cele/{cel_id}/status")
    def status(cel_id: int, body: ZmianaStatusu, request: Request, uz: Uzytkownik = auth.wymagaj("cele.proponuj")) -> Cel:
        """Pracownik: „w_realizacji” i zgłoszenie osiągnięcia. Przełożony: także potwierdzenie
        osiągnięcia i porzucenie. Zakazane przejście: 409, zmiana zastrzeżona dla przełożonego: 403."""
        cel, rekord = cel_z_osoba(request, cel_id, uz, "cele.proponuj")
        kto = strona(uz, rekord)
        return wykonaj(request, uz, cel, lambda: zmien_status(
            request.app.state.baza, cel, body.status, kto, datetime.now(UTC)))

    @r.get("/pracownicy/{osoba_id}/cele/podpowiedzi")
    def podpowiedzi(osoba_id: str, request: Request, uz: Uzytkownik = auth.wymagaj("cele.czytaj")) -> PodpowiedziCelow:
        """Regułowe propozycje ze wskaźników ocenionych poniżej oczekiwań w ostatniej ocenie sporządzonej
        na piśmie (reguły ``rozwoj.yaml``). Nic nie zapisuje."""
        osoba(osoba_id, uz, "cele.czytaj")
        baza = request.app.state.baza
        w = baza.execute(
            "SELECT id FROM procesy WHERE osoba_id = ? AND krok >= ? AND krok2 IS NOT NULL ORDER BY id DESC LIMIT 1",
            (osoba_id, ZRODLO_PODPOWIEDZI_OD_KROKU),
        ).fetchone()
        if w is None:
            return PodpowiedziCelow(proces_id=None, komunikat="Podpowiedzi pojawią się po pierwszej ocenie sporządzonej w aplikacji.")
        proces = wczytaj_proces(baza, w[0])
        oceny, decyzje = _wczytaj_dane(baza, proces.id)
        metodyki = request.app.state.metodyki
        stan = zbuduj_stan(
            proces.id, proces.sciezka, proces.arkusz, proces.krok2, oceny, decyzje, stan2.model,
            metodyki.konfiguracja(metodyki.dla_procesu(proces.id)),
        )
        konf = request.app.state.rozwoj
        wynik = zaproponuj(
            DaneRozwoju(sciezka=proces.sciezka, wskazniki=[OcenaWskaznika.model_validate(x.model_dump()) for x in stan.dla_rozwoju]),
            konf,
        )
        obszary = sorted((p for p in wynik.propozycje if p.typ == "OBSZAR_ROZWOJOWY"), key=lambda p: p.poziom)[:3]
        return PodpowiedziCelow(
            proces_id=proces.id,
            komunikat=None if obszary else "W ostatniej ocenie żaden wskaźnik nie jest poniżej oczekiwań.",
            podpowiedzi=[
                PodpowiedzCelu(
                    nazwa=p.wskaznik,
                    opis=("Proponowane formy rozwoju: " + ", ".join(f.nazwa for f in p.formy)) if p.formy else None,
                    wskaznik_id=p.wskaznik_id,
                    kompetencja=p.kompetencja,
                    poziom=p.poziom,
                    podstawa=f"{p.kompetencja} · {p.wskaznik}: {p.poziom} (poniżej oczekiwań)",
                    adnotacje=konf.reguly[p.regula].adnotacje,
                )
                for p in obszary
            ],
        )

    return r
