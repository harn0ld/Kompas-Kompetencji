"""Cele rozwojowe pracownika (#10, spec #2): treść, status, akceptacja przełożonego.

Cele należą do pracownika, nie do procesu oceny. Przełącznik ``pracownik_moze_edytowac``
(``konfiguracja/cele.yaml``) decyduje, czy pracownik tworzy i zmienia cele; akceptację,
odrzucenie z komentarzem i potwierdzenie osiągnięcia zawsze daje przełożony. Historia zmian
idzie do dziennika z core (zasób ``cel``).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, Field

Status = Literal["propozycja", "zatwierdzony", "w_realizacji", "osiągnięty", "porzucony", "odrzucony"]
Strona = Literal["przelozony", "pracownik"]
KONCOWE: set[str] = {"osiągnięty", "porzucony"}

# Dozwolone przejścia: (kto, na jaki status) → z jakich statusów. Pozostałe dają 409, a niedozwolone
# dla strony (np. pracownik porzuca cel) 403. Zgłoszenie osiągnięcia przez pracownika nie zmienia
# statusu, tylko zapisuje ``zgloszono_osiagniecie`` do potwierdzenia przez przełożonego.
PRZEJSCIA: dict[tuple[Strona, str], set[str]] = {
    ("przelozony", "zatwierdzony"): {"propozycja"},
    ("przelozony", "odrzucony"): {"propozycja"},
    ("przelozony", "w_realizacji"): {"zatwierdzony"},
    ("przelozony", "osiągnięty"): {"zatwierdzony", "w_realizacji"},
    ("przelozony", "porzucony"): {"propozycja", "zatwierdzony", "w_realizacji", "odrzucony"},
    ("pracownik", "w_realizacji"): {"zatwierdzony"},
    ("pracownik", "osiągnięty"): {"zatwierdzony", "w_realizacji"},
}


class _Regula(BaseModel):
    id: str
    opis: str
    adnotacje: list[SourceRef]


class KonfiguracjaCelow(BaseModel):
    pracownik_moze_edytowac: bool
    regula: _Regula

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaCelow:
        return cls.model_validate(yaml.safe_load(Path(plik).read_text(encoding="utf-8")))


class TrescCelu(BaseModel):
    nazwa: str = Field(min_length=1, max_length=200)
    opis: str | None = Field(default=None, max_length=2000)
    wskaznik_id: str | None = None
    """Wskaźnik z modelu kompetencji (opcjonalnie); nieistniejący daje 422."""
    miernik: str | None = Field(default=None, max_length=500)
    termin: date | None = None


class Odrzucenie(BaseModel):
    komentarz: str = Field(min_length=1, max_length=2000)


class ZmianaStatusu(BaseModel):
    status: Literal["w_realizacji", "osiągnięty", "porzucony"]


class WpisHistorii(BaseModel):
    czas: datetime
    autor: str
    zmiany: dict[str, dict]


class Cel(TrescCelu):
    id: int
    osoba_id: str
    status: Status
    komentarz: str | None = None
    """Komentarz przełożonego (wymagany przy odrzuceniu)."""
    zgloszono_osiagniecie: datetime | None = None
    autor: str
    utworzono: datetime
    zmieniono: datetime
    historia: list[WpisHistorii] = Field(default_factory=list)


class PodpowiedzCelu(BaseModel):
    """Propozycja do przyjęcia; nic się nie zapisuje, dopóki ktoś jej nie doda jako celu."""

    nazwa: str
    opis: str | None
    wskaznik_id: str | None
    kompetencja: str
    poziom: int
    podstawa: str
    """Np. „Współpraca · Dbanie o przepływ informacji: 3 (poniżej oczekiwań)”."""
    adnotacje: list[SourceRef]


class PodpowiedziCelow(BaseModel):
    proces_id: int | None
    komunikat: str | None = None
    podpowiedzi: list[PodpowiedzCelu] = Field(default_factory=list)


class BladCelu(Exception):
    def __init__(self, kod: int, komunikat: str) -> None:
        super().__init__(komunikat)
        self.kod = kod
        self.komunikat = komunikat


_POLA = "id, osoba_id, nazwa, opis, wskaznik_id, miernik, termin, status, komentarz, zgloszono_osiagniecie, autor, utworzono, zmieniono"
_TRESC = ("nazwa", "opis", "wskaznik_id", "miernik", "termin")


def _z_wiersza(w: tuple) -> Cel:
    return Cel.model_validate(dict(zip([p.strip() for p in _POLA.split(",")], w)))


def wczytaj(baza: sqlite3.Connection, cel_id: int) -> Cel | None:
    w = baza.execute(f"SELECT {_POLA} FROM cele WHERE id = ?", (cel_id,)).fetchone()
    return _z_wiersza(w) if w else None


def lista(baza: sqlite3.Connection, osoba_id: str) -> list[Cel]:
    return [_z_wiersza(w) for w in baza.execute(f"SELECT {_POLA} FROM cele WHERE osoba_id = ? ORDER BY id", (osoba_id,))]


def do_dziennika(c: Cel) -> dict:
    return c.model_dump(mode="json", include={*_TRESC, "status", "komentarz", "zgloszono_osiagniecie"})


def utworz(baza: sqlite3.Connection, osoba_id: str, tresc: TrescCelu, strona: Strona, autor: str, teraz: datetime) -> int:
    status = "zatwierdzony" if strona == "przelozony" else "propozycja"
    with baza:
        cur = baza.execute(
            "INSERT INTO cele (osoba_id, nazwa, opis, wskaznik_id, miernik, termin, status, autor, utworzono, zmieniono)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (osoba_id, tresc.nazwa, tresc.opis, tresc.wskaznik_id, tresc.miernik,
             tresc.termin.isoformat() if tresc.termin else None, status, autor, teraz.isoformat(), teraz.isoformat()),
        )
    return cur.lastrowid


def edytuj(baza: sqlite3.Connection, cel: Cel, tresc: TrescCelu, strona: Strona, teraz: datetime) -> None:
    """Przełożony zmienia treść bez zmiany statusu; zmiana pracownika wraca do akceptacji („propozycja”)."""
    if cel.status in KONCOWE:
        raise BladCelu(409, f"Cel ma status „{cel.status}” i nie można go zmienić.")
    status = cel.status if strona == "przelozony" else "propozycja"
    zgloszono = cel.zgloszono_osiagniecie if strona == "przelozony" else None
    with baza:
        baza.execute(
            "UPDATE cele SET nazwa = ?, opis = ?, wskaznik_id = ?, miernik = ?, termin = ?, status = ?,"
            " zgloszono_osiagniecie = ?, zmieniono = ? WHERE id = ?",
            (tresc.nazwa, tresc.opis, tresc.wskaznik_id, tresc.miernik,
             tresc.termin.isoformat() if tresc.termin else None, status,
             zgloszono.isoformat() if zgloszono else None, teraz.isoformat(), cel.id),
        )


def zmien_status(
    baza: sqlite3.Connection, cel: Cel, nowy: str, strona: Strona, teraz: datetime, komentarz: str | None = None,
) -> None:
    dozwolone = PRZEJSCIA.get((strona, nowy))
    if dozwolone is None:
        raise BladCelu(403, "Tę zmianę statusu wykonuje przełożony.")
    if cel.status not in dozwolone:
        raise BladCelu(409, f"Nie można zmienić statusu „{cel.status}” na „{nowy}”.")
    if strona == "pracownik" and nowy == "osiągnięty":
        # Pracownik tylko zgłasza osiągnięcie; status zmienia przełożony.
        pola, wartosci = "zgloszono_osiagniecie = ?", [teraz.isoformat()]
    else:
        pola, wartosci = "status = ?", [nowy]
        if komentarz is not None:
            pola += ", komentarz = ?"
            wartosci.append(komentarz)
    with baza:
        baza.execute(f"UPDATE cele SET {pola}, zmieniono = ? WHERE id = ?", (*wartosci, teraz.isoformat(), cel.id))
