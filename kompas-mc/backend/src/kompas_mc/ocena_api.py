"""API kroków 3–5 (#31): oceny wskaźników z przykładami, sugestia poziomu, decyzja przełożonego."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik
from pydantic import TypeAdapter

from .krok2_api import StanKroku2
from .metodyka import RejestrMetodyk
from .ocena import (
    ZapisRozmowy,
    BladOceny,
    Decyzja,
    KonfiguracjaOceny,
    OcenaWskaznika,
    SamoocenaWskaznika,
    StanOceny,
    ZapisDecyzji,
    ZapisWskaznikow,
    scal_decyzje,
    scal_oceny,
    zbuduj_stan,
)
from .procesy import ProcesOceny, dzien_urzedowy, wczytaj_proces
from .qnt import MockQnt
from .samoocena import rozbieznosc, ukryj_przed_przekazaniem, wczytaj as wczytaj_samoocene

_W_TOKU = "id = ? AND status = 'W_TOKU'"
"""Warunek każdego zapisu: równoległe zakończenie procesu wygrywa ze spóźnionym zapisem (#114)."""
_OCENY = TypeAdapter(dict[str, OcenaWskaznika])
_DECYZJE = TypeAdapter(dict[str, Decyzja])


def _wczytaj_dane(baza, proces_id: int) -> tuple[dict[str, OcenaWskaznika], dict[str, Decyzja]]:
    o, d = baza.execute(
        "SELECT oceny_wskaznikow, decyzje FROM procesy WHERE id = ?", (proces_id,)
    ).fetchone()
    return (_OCENY.validate_json(o) if o else {}), (_DECYZJE.validate_json(d) if d else {})


def _wczytaj_rozmowe(baza, proces_id: int) -> ZapisRozmowy | None:
    (r,) = baza.execute("SELECT rozmowa FROM procesy WHERE id = ?", (proces_id,)).fetchone()
    return ZapisRozmowy.model_validate_json(r) if r else None


def router(auth: Autoryzacja, qnt: MockQnt, stan2: StanKroku2) -> APIRouter:
    """Konfiguracja kroków 3–5 pochodzi z rejestru metodyk (``app.state.metodyki``, #39)."""
    r = APIRouter(prefix="/api", tags=["kroki 3–5: zachowania, sugestia, decyzja"])

    def proces_dostepny(request: Request, proces_id: int, uz: Uzytkownik, akcja: str) -> ProcesOceny:
        proces = wczytaj_proces(request.app.state.baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        p = qnt.pracownik(proces.osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", p.model_dump(), akcja)
        if proces.krok2 is None:
            raise HTTPException(409, "Najpierw zapisz kryteria i wskaźniki (krok 2).")
        return proces

    def rejestr(request: Request) -> RejestrMetodyk:
        return request.app.state.metodyki

    def konf_procesu(request: Request, proces: ProcesOceny) -> KonfiguracjaOceny:
        """Wersja metodyki przypięta do procesu (#39), a przed pierwszym zapisem – aktywna."""
        r = rejestr(request)
        return r.konfiguracja(r.dla_procesu(proces.id))

    def stan(request: Request, proces: ProcesOceny) -> StanOceny:
        oceny, decyzje = _wczytaj_dane(request.app.state.baza, proces.id)
        wynik = zbuduj_stan(
            proces.id, proces.sciezka, proces.arkusz, proces.krok2, oceny, decyzje, stan2.model,
            konf_procesu(request, proces),
        )
        wynik.rozmowa = _wczytaj_rozmowe(request.app.state.baza, proces.id)
        return wynik

    def zapisz(
        request: Request, uz: Uzytkownik, proces: ProcesOceny, kolumna: str, wartosc: str, przed, po
    ) -> StanOceny:
        baza = request.app.state.baza
        metodyka = rejestr(request).przypnij(proces.id)
        with baza:
            if not baza.execute(f"UPDATE procesy SET {kolumna} = ? WHERE {_W_TOKU}", (wartosc, proces.id)).rowcount:
                raise HTTPException(409, "Proces nie jest w toku")
        nowy = stan(request, proces)
        krok = 5 if nowy.kompletnosc.wszystkie_decyzje else 3
        with baza:
            baza.execute(f"UPDATE procesy SET krok = MAX(krok, ?) WHERE {_W_TOKU}", (krok, proces.id))
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(uz.login, "proces", str(proces.id), przed, po, metodyka.id)
        return nowy

    @r.get("/procesy/{proces_id}/ocena")
    def odczyt(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.tresc")
    ) -> StanOceny:
        """Wskaźniki wybrane w kroku 2 z opisami 5 zachowań, oceny i przykłady, sugestia poziomu
        każdego kryterium (z etykietą metodyki) i decyzja przełożonego. Przełożony widzi też status
        samooceny, a po jej przekazaniu odpowiedź pracownika i flagę rozbieżności przy wskaźniku (#8);
        sugestia liczy się wyłącznie z ocen przełożonego."""
        proces = proces_dostepny(request, proces_id, uz, "ocena.tresc")
        p = qnt.pracownik(proces.osoba_id)
        # Pracownik zobaczy ocenę przełożonego dopiero po przekazaniu samooceny, żeby jej nie przepisywał.
        if p is not None:
            ukryj_przed_przekazaniem(auth, uz, p.model_dump(), request.app.state.baza, proces)
        wynik = stan(request, proces)
        if p is not None and auth.moze(uz, "pracownik", p.model_dump(), "samoocena.czytaj"):
            status, _, pozycje = wczytaj_samoocene(request.app.state.baza, proces.id)
            wynik.samoocena_status = status
            if status == "przekazana":
                prog = request.app.state.samoocena.prog_rozbieznosci
                for k in wynik.kryteria:
                    for w in k.wskazniki:
                        s = pozycje.get(w.wskaznik_id)
                        if s is not None:
                            w.samoocena = SamoocenaWskaznika(
                                poziom=s.poziom, brak_zdania=s.brak_zdania, przyklad=s.przyklad
                            )
                        w.rozbieznosc = rozbieznosc(s, w.ocena, prog)
        return wynik

    @r.put("/procesy/{proces_id}/ocena/wskazniki")
    def wskazniki(
        proces_id: int,
        body: ZapisWskaznikow,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> StanOceny:
        """Krok 3: wybór opisu zachowania (1/3/5/7/9) albo „brak podstaw do oceny” i przykłady
        S-D-R. Scala z poprzednim stanem; ``null`` usuwa ocenę wskaźnika."""
        proces = proces_dostepny(request, proces_id, uz, "ocena.prowadz")
        if proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")
        obecne, _ = _wczytaj_dane(request.app.state.baza, proces.id)
        try:
            nowe = scal_oceny(obecne, body, proces.krok2)
        except BladOceny as e:
            raise HTTPException(422, {"komunikat": "Niepoprawne oceny wskaźników.", "bledy": e.args[0]})
        zrzut = lambda d: json.loads(_OCENY.dump_json(d))  # noqa: E731
        return zapisz(
            request, uz, proces, "oceny_wskaznikow", _OCENY.dump_json(nowe).decode(),
            {"oceny_wskaznikow": zrzut(obecne)}, {"oceny_wskaznikow": zrzut(nowe)},
        )

    @r.put("/procesy/{proces_id}/ocena/decyzje")
    def decyzje(
        proces_id: int,
        body: ZapisDecyzji,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> StanOceny:
        """Krok 5: ocena cząstkowa kryterium wybrana przez przełożonego. Punkty ze skali ścieżki;
        uzasadnienie odejścia od sugestii jest opcjonalne. ``null`` cofa decyzję."""
        proces = proces_dostepny(request, proces_id, uz, "ocena.prowadz")
        if proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")
        _, obecne = _wczytaj_dane(request.app.state.baza, proces.id)
        try:
            nowe = scal_decyzje(
                obecne, body, stan(request, proces), konf_procesu(request, proces), uz.login, datetime.now(UTC)
            )
        except BladOceny as e:
            raise HTTPException(422, {"komunikat": "Niepoprawne decyzje.", "bledy": e.args[0]})
        zrzut = lambda d: {k: {"punkty": v.punkty, "uzasadnienie": v.uzasadnienie} for k, v in d.items()}  # noqa: E731
        return zapisz(
            request, uz, proces, "decyzje", _DECYZJE.dump_json(nowe).decode(),
            {"decyzje": zrzut(obecne)}, {"decyzje": zrzut(nowe)},
        )

    @r.put("/procesy/{proces_id}/ocena/rozmowa")
    def rozmowa(
        proces_id: int,
        body: ZapisRozmowy,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> StanOceny:
        """Rozmowa oceniająca (§ 10): notatki tematów, szkic informacji zwrotnej i data. Zastępuje
        poprzedni zapis. Data rozmowy przy komplecie ocen cząstkowych kończy rozmowę: proces przechodzi
        do oceny na piśmie (krok 6). 422, gdy data jest z przyszłości albo sprzed zapoznania z kryteriami."""
        proces = proces_dostepny(request, proces_id, uz, "ocena.prowadz")
        if proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")
        zapoznanie = proces.krok2.zapoznanie if proces.krok2 else None
        if body.data and (body.data > dzien_urzedowy(datetime.now(UTC)) or (zapoznanie and body.data < zapoznanie)):
            raise HTTPException(422, "Data rozmowy musi przypadać od zapoznania z kryteriami do dziś.")
        przed = _wczytaj_rozmowe(request.app.state.baza, proces.id)
        nowy = zapisz(
            request, uz, proces, "rozmowa", body.model_dump_json(),
            {"rozmowa_data": przed.data.isoformat() if przed and przed.data else None},
            {"rozmowa_data": body.data.isoformat() if body.data else None},
        )
        if body.data and nowy.kompletnosc.wszystkie_decyzje:
            baza = request.app.state.baza
            with baza:
                baza.execute(f"UPDATE procesy SET krok = MAX(krok, 6) WHERE {_W_TOKU}", (proces.id,))
        return nowy

    return r
