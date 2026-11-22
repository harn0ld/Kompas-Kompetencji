"""Panel HR/administratora (#38): procesy, najbliższe terminy, zagrożone, przypomnienia.

HR widzi metadane procesu (ścieżka, arkusz, krok, status, termin), nigdy treści ocen ani
notatek przełożonego. Terminy liczą reguły ścieżek (#32 ocena okresowa, #34 pierwsza ocena):
panel przyjmuje je przez ``ZrodloTerminow``, więc podpięcie reguł nie zmienia panelu.
Przypomnienia trafiają do mockowanej skrzynki nadawczej (bez wysyłki e-mail).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date, datetime
from typing import Literal

from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, Field

from .pierwsza_ocena import ZapisDanychPierwszej, uzupelnij_z_kadr
from .procesy import ProcesOceny, dzien_urzedowy, dzien_ustalenia_kryteriow
from .qnt import Pracownik
from .terminy_okresowej import (
    KonfiguracjaTerminow,
    dane_terminow_procesu,
    oblicz_terminy,
)
from .terminy_pierwszej import KonfiguracjaTerminowPierwszej, oblicz_terminy_pierwszej

PROG_ZAGROZONY_DNI = 7
"""Kryterium #38: proces z terminem w ciągu 7 dni (lub po terminie) jest zagrożony."""


class Termin(BaseModel):
    nazwa: str
    data: date
    adnotacje: list[SourceRef] = Field(default_factory=list)


ZrodloTerminow = Callable[[ProcesOceny, Pracownik, date], list[Termin]]
"""Terminy procesu na dany dzień. Reguły dostarczają #32 i #34."""


def brak_terminow(proces: ProcesOceny, pracownik: Pracownik, dzis: date) -> list[Termin]:
    """Domyślne źródło do czasu podpięcia reguł z #32/#34."""
    return []


def terminy_z_regul(
    konf_okresowej: KonfiguracjaTerminow,
    konf_pierwszej: KonfiguracjaTerminowPierwszej,
    baza: sqlite3.Connection,
) -> ZrodloTerminow:
    """Udostępnij terminy obu ścieżek bez danych merytorycznych oceny."""

    def zrodlo(proces: ProcesOceny, p: Pracownik, dzis: date) -> list[Termin]:
        if proces.sciezka == "pierwsza":
            zapis, = baza.execute("SELECT pierwsza_ocena FROM procesy WHERE id = ?", (proces.id,)).fetchone()
            dane = uzupelnij_z_kadr(ZapisDanychPierwszej.wczytaj(zapis).dane, p)
            try:
                t = oblicz_terminy_pierwszej(p, dane, konf_pierwszej)
            except ValueError:
                return []
            return [
                Termin(nazwa=nazwa, data=termin.data, adnotacje=[k.regula.zrodlo for k in termin.slad])
                for wykonano, nazwa, termin in (
                    (t.data_rozmowy_wstepnej, "rozmowa wstępna (§ 3)", t.termin_rozmowy_wstepnej),
                    (dane.data_zlozenia_sprawozdania or dane.sprawozdanie_niezlozone,
                     "złożenie sprawozdania (§ 4–5)", t.termin_sprawozdania_do),
                    (dane.data_sporzadzenia_oceny, "dokonanie pierwszej oceny", t.pierwsza_ocena_do),
                )
                if not wykonano and termin is not None
            ]
        # Te same dane terminów co wynik i cykl: zapisana zmiana terminu (§ 8) i daty z kroku 2 (zgłoszenie 124).
        zapis_wyniku, = baza.execute("SELECT wynik_okresowy FROM procesy WHERE id = ?", (proces.id,)).fetchone()
        try:
            t = oblicz_terminy(p, dane_terminow_procesu(
                zapis_wyniku,
                data_ustalenia_kryteriow=dzien_ustalenia_kryteriow(proces.krok2) if proces.krok2 else None,
                data_zapoznania_z_kryteriami=proces.krok2.zapoznanie if proces.krok2 else None,
            ), konf_okresowej)
        except ValueError:
            return []
        wynik = []
        # Termin kryteriów sprzed rozpoczęcia procesu w aplikacji dotyczy czynności
        # wykonanych poza nią – nie oznaczamy go jako zaległego.
        if t.termin_kryteriow and proces.krok2 is None and t.termin_kryteriow.data >= min(dzien_urzedowy(proces.rozpoczeto), dzis):
            wynik.append(Termin(nazwa="ustalenie kryteriów i rozmowa (§ 7)", data=t.termin_kryteriow.data))
        sporzadzenie = t.termin_sporzadzenia_oceny or t.termin_bazowy
        if sporzadzenie:
            wynik.append(Termin(nazwa="sporządzenie oceny na piśmie", data=sporzadzenie.data))
        return wynik

    return zrodlo


class WierszPanelu(BaseModel):
    """Wiersz listy HR. Celowo bez ocen, przykładów, decyzji i notatek."""

    proces_id: int
    osoba_id: str
    osoba: str
    stanowisko: str
    przelozony_id: str
    sciezka: Literal["pierwsza", "okresowa"]
    arkusz: str
    krok: int
    status: str
    najblizszy_termin: Termin | None
    dni_do_terminu: int | None
    zagrozony: bool
    komunikat: str | None = None


class PropozycjaPrzypomnienia(BaseModel):
    proces_id: int
    adresat: str
    """osoba_id przełożonego prowadzącego proces."""
    tresc: str
    termin: Termin


class NowePrzypomnienie(BaseModel):
    proces_id: int
    adresat: str = Field(min_length=1, max_length=50)
    tresc: str = Field(min_length=1, max_length=2000)


class Przypomnienie(BaseModel):
    id: int
    proces_id: int
    adresat: str
    tresc: str
    nadawca: str
    wyslano: datetime


def wiersz(proces: ProcesOceny, p: Pracownik, terminy: list[Termin], dzis: date) -> WierszPanelu:
    nadchodzace = sorted(terminy, key=lambda t: t.data)
    t = nadchodzace[0] if nadchodzace else None
    dni = (t.data - dzis).days if t else None
    zakonczony = proces.status == "ZAKONCZONY"
    return WierszPanelu(
        proces_id=proces.id,
        osoba_id=p.osoba_id,
        osoba=f"{p.imie} {p.nazwisko}",
        stanowisko=p.stanowisko,
        przelozony_id=p.przelozony_id,
        sciezka=proces.sciezka,
        arkusz=proces.arkusz,
        krok=proces.krok,
        status=proces.status,
        najblizszy_termin=t,
        dni_do_terminu=dni,
        zagrozony=(not zakonczony and dni is not None and dni <= PROG_ZAGROZONY_DNI),
        komunikat=None if t or zakonczony else "Brak terminu: brak danych do jego wyliczenia.",
    )


def propozycja(w: WierszPanelu) -> PropozycjaPrzypomnienia | None:
    if not w.zagrozony or w.najblizszy_termin is None:
        return None
    t = w.najblizszy_termin
    def dni(n: int) -> str:
        return "1 dzień" if n == 1 else f"{n} dni"

    kiedy = (
        f"minął {dni(-w.dni_do_terminu)} temu" if w.dni_do_terminu < 0
        else "upływa dziś" if w.dni_do_terminu == 0
        else f"upływa za {dni(w.dni_do_terminu)}"
    )
    return PropozycjaPrzypomnienia(
        proces_id=w.proces_id,
        adresat=w.przelozony_id,
        tresc=(
            f"Przypomnienie: w procesie oceny ({w.sciezka}, arkusz {w.arkusz}) pracownika "
            f"{w.osoba} termin „{t.nazwa}” ({t.data.strftime("%d.%m.%Y")}) {kiedy}."
        ),
        termin=t,
    )


# --- skrzynka nadawcza (mock) -----------------------------------------------------


def _tabela(baza: sqlite3.Connection) -> None:
    baza.execute(
        "CREATE TABLE IF NOT EXISTS skrzynka_nadawcza (id INTEGER PRIMARY KEY,"
        " proces_id INTEGER NOT NULL, adresat TEXT NOT NULL, tresc TEXT NOT NULL,"
        " nadawca TEXT NOT NULL, wyslano TEXT NOT NULL)"
    )


def wyslij(baza: sqlite3.Connection, nowe: NowePrzypomnienie, nadawca: str, teraz: datetime) -> Przypomnienie:
    _tabela(baza)
    with baza:
        cur = baza.execute(
            "INSERT INTO skrzynka_nadawcza (proces_id, adresat, tresc, nadawca, wyslano)"
            " VALUES (?, ?, ?, ?, ?)",
            (nowe.proces_id, nowe.adresat, nowe.tresc, nadawca, teraz.isoformat()),
        )
    return Przypomnienie(id=cur.lastrowid, nadawca=nadawca, wyslano=teraz, **nowe.model_dump())


def skrzynka(baza: sqlite3.Connection, proces_id: int | None = None) -> list[Przypomnienie]:
    _tabela(baza)
    sql = "SELECT id, proces_id, adresat, tresc, nadawca, wyslano FROM skrzynka_nadawcza"
    arg: tuple = ()
    if proces_id is not None:
        sql, arg = sql + " WHERE proces_id = ?", (proces_id,)
    return [
        Przypomnienie(id=i, proces_id=pid, adresat=a, tresc=t, nadawca=n, wyslano=datetime.fromisoformat(w))
        for i, pid, a, t, n, w in baza.execute(sql + " ORDER BY id", arg).fetchall()
    ]
