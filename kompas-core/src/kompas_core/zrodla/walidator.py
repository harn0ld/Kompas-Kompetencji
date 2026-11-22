"""Walidator adnotacji: czy każdy cytat występuje dosłownie w korpusie.

Normalizacja jest celowo wąska: tylko białe znaki i dzielenie wyrazów na końcu
wiersza (``zatrudnio-\\nnego`` == ``zatrudnionego``). Każda inna różnica, w tym
wielkość liter i interpunkcja, oznacza brak pokrycia. Dodatkowo tekst jest
sprowadzany do postaci Unicode NFC, bo ta sama litera z PDF może być zapisana jako
„a” + ogonek; to różnica kodowania, nie treści.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from enum import StrEnum
from functools import lru_cache

from pydantic import BaseModel

from .korpus import Korpus
from .model import ElementAdnotowany, SourceRef


class KodBledu(StrEnum):
    BRAK_ADNOTACJI = "BRAK_ADNOTACJI"
    BRAK_POKRYCIA = "BRAK_POKRYCIA"
    """Cytatu nie ma w dokumencie ``doc_id`` (ani w wersji ``doc_version``, jeśli podana)."""
    NIEZNANY_DOKUMENT = "NIEZNANY_DOKUMENT"
    NIEPOPRAWNA_ADNOTACJA = "NIEPOPRAWNA_ADNOTACJA"
    """Adnotacja łamie reguły kategorii (np. brak cytatu przy PRZEPIS)."""


class BladWalidacji(BaseModel):
    element_id: str | None
    kod: KodBledu
    komunikat: str
    adnotacja: SourceRef | None = None


class WynikWalidacji(BaseModel):
    sprawdzone_elementy: int
    sprawdzone_cytaty: int
    bledy: list[BladWalidacji]

    @property
    def ok(self) -> bool:
        return not self.bledy


_MIEKKI_LACZNIK = re.compile(r"­\s*")
_LACZNIK_NA_KONCU_WIERSZA = re.compile(r"-[ \t ]*\r?\n\s*")
_BIALE = re.compile(r"\s+")
_PUNKTOR = re.compile("[•]")
"""Punktory wyliczeń z PDF poradników (font Symbol: U+F0B7, U+F02D) i „•”; model cytuje listę bez nich."""


def _nfc(tekst: str) -> str:
    return _PUNKTOR.sub(" ", _MIEKKI_LACZNIK.sub("", unicodedata.normalize("NFC", tekst)))


def normalizuj(tekst: str) -> str:
    """Normalizacja do porównań: dzielenie wyrazów na końcu wiersza, punktory wyliczeń i białe znaki.

    ``"zatrudnio-\\nnego"`` → ``"zatrudnionego"``.
    """
    tekst = _LACZNIK_NA_KONCU_WIERSZA.sub("", _nfc(tekst))
    return _BIALE.sub(" ", tekst).strip()


def _normalizuj_z_lacznikiem(tekst: str) -> str:
    """Wariant dla wyrazów złożonych łamanych na łączniku: ``"biało-\\nczerwony"``
    → ``"biało-czerwony"``."""
    tekst = _LACZNIK_NA_KONCU_WIERSZA.sub("-", _nfc(tekst))
    return _BIALE.sub(" ", tekst).strip()


def cytat_w_tekscie(cytat: str, tekst: str) -> bool:
    """Czy cytat (po normalizacji) występuje w danym tekście, np. w jednym fragmencie."""
    if not normalizuj(cytat):
        return False
    a, b = _warianty(tekst)
    return normalizuj(cytat) in a or _normalizuj_z_lacznikiem(cytat) in b


@lru_cache(maxsize=256)
def _warianty(tekst: str) -> tuple[str, str]:
    return normalizuj(tekst), _normalizuj_z_lacznikiem(tekst)


def cytat_w_korpusie(
    cytat: str, korpus: Korpus, doc_id: str | None = None, doc_version: str | None = None
) -> bool:
    """Czy cytat (po normalizacji) występuje w dokumencie lub w całym korpusie.

    Bez ``doc_version`` sprawdzane są wszystkie wersje dokumentu.
    """
    if not normalizuj(cytat):
        return False
    if doc_id is None:
        dokumenty = {(f.doc_id, f.doc_version) for f in korpus.fragmenty}
    elif doc_version is None:
        dokumenty = {(doc_id, w) for w in korpus.wersje(doc_id)}
    else:
        dokumenty = {(doc_id, doc_version)}
    return any(cytat_w_tekscie(cytat, korpus.tekst_dokumentu(d, w)) for d, w in dokumenty)


def waliduj_adnotacje(
    ref: SourceRef, korpus: Korpus, element_id: str | None = None
) -> list[BladWalidacji]:
    """Sprawdza cytat adnotacji. Cytat jest sprawdzany zawsze, gdy jest podany,
    także przy kategoriach, które go nie wymagają."""
    if ref.cytat_doslowny is None:
        return []

    def blad(kod: KodBledu, komunikat: str) -> list[BladWalidacji]:
        return [BladWalidacji(element_id=element_id, kod=kod, komunikat=komunikat, adnotacja=ref)]

    if ref.doc_id is not None:
        wersje = korpus.wersje(ref.doc_id)
        if not wersje:
            return blad(KodBledu.NIEZNANY_DOKUMENT, f"brak dokumentu {ref.doc_id} w korpusie")
        if ref.doc_version is not None and ref.doc_version not in wersje:
            return blad(
                KodBledu.NIEZNANY_DOKUMENT,
                f"brak wersji {ref.doc_version} dokumentu {ref.doc_id} (są: {wersje})",
            )
    if not cytat_w_korpusie(ref.cytat_doslowny, korpus, ref.doc_id, ref.doc_version):
        gdzie = ref.doc_id or "korpusie"
        return blad(
            KodBledu.BRAK_POKRYCIA,
            f"cytatu nie ma w {gdzie}: „{_skrot(ref.cytat_doslowny)}”",
        )
    return []


def waliduj_elementy(elementy: Iterable[ElementAdnotowany], korpus: Korpus) -> WynikWalidacji:
    """Każdy element ma ≥1 adnotację, a każdy cytat jest w korpusie."""
    bledy: list[BladWalidacji] = []
    n_el = n_cyt = 0
    for el in elementy:
        n_el += 1
        if not el.adnotacje:
            bledy.append(
                BladWalidacji(
                    element_id=el.id, kod=KodBledu.BRAK_ADNOTACJI, komunikat="element bez adnotacji"
                )
            )
        for ref in el.adnotacje:
            if ref.cytat_doslowny is not None:
                n_cyt += 1
            bledy.extend(waliduj_adnotacje(ref, korpus, el.id))
    return WynikWalidacji(sprawdzone_elementy=n_el, sprawdzone_cytaty=n_cyt, bledy=bledy)


def _skrot(tekst: str, n: int = 80) -> str:
    tekst = normalizuj(tekst)
    return tekst if len(tekst) <= n else tekst[: n - 1] + "…"
