"""Kontrakt LLM: zapytanie z fragmentami korpusu, odpowiedź z cytatami, wpis logu.

Zasada: wejście to wyłącznie fragmenty korpusu z ID, a wyjście musi wskazywać ID
fragmentów i dosłowne cytaty z nich. Odpowiedź z cytatem bez pokrycia jest
odrzucana i system przechodzi do następnego dostawcy (fallback).
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..zrodla.model import Fragment


class Tryb(StrEnum):
    """Znacznik pokazywany użytkownikowi przy każdej odpowiedzi."""

    NA_ZYWO = "NA_ŻYWO"
    ZAPISANE = "ZAPISANE"
    EKSTRAKCYJNE = "EKSTRAKCYJNE"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Zapytanie(_Model):
    """Wejście dla dostawcy.

    ``operacja`` to nazwa dozwolonej operacji ustalona przez wersję (np.
    ``"mapowanie"``, ``"cytaty_dowody"``, ``"diff_przepisow"``, ``"asystent"``).
    ``katalog`` to dozwolone ID wyboru (np. ID kryteriów); pusty = bez wyboru.
    """

    operacja: str
    prompt_wersja: str
    pytanie: str
    fragmenty: list[Fragment]
    katalog: list[str] = Field(default_factory=list)
    rola: str = ""
    """Prompt główny aplikacji (kim jest asystent, w czym pomaga, ton, granice); idzie do modelu
    przed wspólną instrukcją techniczną. Pusty = sama instrukcja techniczna."""


class Cytat(_Model):
    fragment_id: str
    cytat: str


class Odpowiedz(_Model):
    """Wyjście dostawcy.

    ``tresc`` to opcjonalny tekst ułożony wyłącznie z cytowanych fragmentów
    (np. odpowiedź asystenta). ``wybor`` to ID z ``Zapytanie.katalog``.
    """

    cytaty: list[Cytat]
    wybor: list[str] = Field(default_factory=list)
    tresc: str | None = None

    @field_validator("tresc", mode="before")
    @classmethod
    def _tresc_obiekt_jako_tekst(cls, v: object) -> object:
        # #176: modele często zwracają „tresc” jako obiekt JSON zamiast tekstu z JSON-em, o który prosi
        # polecenie; zapisujemy go jako ten sam tekst JSON zamiast odrzucać całą odpowiedź.
        return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v


class WynikLlm(_Model):
    """Odpowiedź po walidacji, z informacją, kto ją dał i w jakim trybie."""

    odpowiedz: Odpowiedz
    dostawca: str
    model: str | None
    tryb: Tryb
    odrzuceni: list[str] = Field(
        default_factory=list, description="dostawcy, których odpowiedź odrzucono przed tą"
    )


class WpisLogu(_Model):
    """Log każdego wywołania (także odrzuconego i zakończonego błędem)."""

    czas: datetime
    operacja: str
    dostawca: str
    model: str | None
    prompt_wersja: str
    fragment_ids: list[str]
    tryb: Tryb
    walidacja_ok: bool
    bledy: list[str] = Field(default_factory=list)
    odpowiedz: Odpowiedz | None = None
