"""Mock systemu kadrowego QNT: fikcyjni pracownicy z ``konfiguracja/qnt.yaml``.

Zakres danych osobowych jest minimalny: imię, nazwisko, stanowisko, komórka, przełożony
oraz fakty kadrowe potrzebne do wyboru ścieżki oceny i terminów. Bez PESEL, adresów
i danych wrażliwych.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OstatniaOcenaOkresowa(_Model):
    data: date
    wynik: Literal["pozytywna", "negatywna"]
    oceny_czastkowe: dict[str, int] = Field(default_factory=dict, exclude=True)
    """Punkty ocen cząstkowych z arkusza w aktach (kompetencja_id → 1/3/5/7/9). Treść oceny: poza
    ``model_dump`` (lista pracowników, HR); udostępnia ją tylko ``/api/zespol/kompetencje`` (#33)."""
    data_zapoznania: date | None = None
    """Data zapoznania ocenianego z oceną (podpis na arkuszu w aktach osobowych, § 12 rozp. 2016).
    Po ocenie negatywnej wyznacza termin ponownej oceny (§ 7 pkt 2, art. 81 ust. 3 ustawy wg poradnika)."""


class ZmianaOceniajacego(_Model):
    data: date
    poprzedni_przelozony: str


class PierwszaOcena(_Model):
    egzamin_sluzba_przygotowawcza: Literal["zaliczony", "nie_dotyczy", "brak"]
    rozmowa_wstepna: date | None = None
    uzgodnienie_zastepstwa: date | None = None


class Nieobecnosc(_Model):
    od: date
    do: date
    rodzaj: str


class Pracownik(_Model):
    osoba_id: str
    imie: str
    nazwisko: str
    stanowisko: str
    symbol_osp: str | None = None
    komorka: str
    przelozony_id: str
    kieruje_pracownikami: bool
    korpus: Literal["urzednik_sc", "pracownik_sc"]
    data_zatrudnienia: date
    data_konca_zatrudnienia: date | None = None
    rodzaj_umowy: Literal["nieokreslony", "okreslony"]
    ostatnia_ocena_okresowa: OstatniaOcenaOkresowa | None = None
    zmiana_oceniajacego: ZmianaOceniajacego | None = None
    pierwsza_ocena: PierwszaOcena | None = None
    absolwent_ksap: bool = False
    wniosek_o_mianowanie: bool | None = None
    zastepstwo: bool = False
    nieobecnosci: list[Nieobecnosc] = []
    oczekiwany_arkusz: Literal["A", "B", "C"] | None = Field(default=None, exclude=True)
    """Tylko do testów; arkusz wylicza reguła § 3 rozp. 2016."""
    scenariusz: str | None = Field(default=None, exclude=True)
    """Opis, co rekord pokazuje na demo; nie jest daną kadrową."""
    demo_od_poczatku: Literal["okresowa", "pierwsza"] | None = None
    """Osoba demo z przyciskiem „Rozpocznij od początku” na pulpicie (#186); wartość mówi, którą ocenę testujemy."""


class MockQnt:
    def __init__(self, pracownicy: list[Pracownik], dzis_demo: date) -> None:
        self.pracownicy = pracownicy
        self.dzis_demo = dzis_demo
        self._po_id = {p.osoba_id: p for p in pracownicy}

    @classmethod
    def z_pliku(cls, plik: str | Path) -> MockQnt:
        dane = yaml.safe_load(Path(plik).read_text(encoding="utf-8"))
        return cls([Pracownik.model_validate(p) for p in dane["pracownicy"]], dane["dzis_demo"])

    def pracownik(self, osoba_id: str) -> Pracownik | None:
        return self._po_id.get(osoba_id)

    def zapisz_ocene_okresowa(self, osoba_id: str, ocena: OstatniaOcenaOkresowa) -> None:
        """Mock zapisu do akt (#72): zakończona ocena z aplikacji staje się ostatnią oceną w kartotece,
        więc cykl liczy następny okres (§ 7 rozp. 2016), a karta i panel HR pokazują nową ocenę.
        Prawdziwe QNT dostałoby ją przez integrację; mock trzyma ją w pamięci i odtwarza z bazy przy starcie."""
        p = self._po_id.get(osoba_id)
        if p is None:
            return
        nowy = p.model_copy(update={"ostatnia_ocena_okresowa": ocena})
        self._po_id[osoba_id] = nowy
        self.pracownicy[self.pracownicy.index(p)] = nowy
