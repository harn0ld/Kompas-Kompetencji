"""Kroki 3–5 (#31): zachowania i przykłady, sugerowany poziom kryterium, decyzja przełożonego.

Czyste funkcje. Metodyka sugestii (mediana, remis, „niewystarczające dane”, mapowanie 5→3)
jest DECYZJĄ_PROJEKTOWĄ z ``konfiguracja/ocena.yaml``. Sugestia nigdy nie wpisuje oceny
cząstkowej; decyzję podejmuje przełożony, uzasadnienie odejścia od sugestii jest opcjonalne (Karol 21.11).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

import yaml
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, Field, field_validator, model_validator

from .kompetencje import Instrukcja, ModelKompetencji
from .krok2 import WyborKroku2

Sciezka = Literal["pierwsza", "okresowa"]
POZIOMY_MODELU = (1, 3, 5, 7, 9)


# ---------------------------------------------------------------- konfiguracja


class Skala(BaseModel):
    punkty: list[int]
    etykiety: dict[int, str]
    adnotacje: list[SourceRef]


class Metodyka(BaseModel):
    id: str
    status: str
    minimalny_udzial_ocenionych: float
    opis: str
    adnotacje: list[SourceRef]

    @property
    def etykieta(self) -> str:
        return f"{self.id} · {self.status}"


class Mapowanie(BaseModel):
    wartosci: dict[int, int]
    adnotacje: list[SourceRef]


class _Przyklady(BaseModel):
    adnotacje: list[SourceRef]
    ostrzezenie_bez_przykladu: str


class KonfiguracjaOceny(BaseModel):
    poziom_oczekiwan: int
    skale: dict[Sciezka, Skala]
    metodyka: Metodyka
    mapowanie_pierwsza: Mapowanie
    przyklady: _Przyklady

    @classmethod
    def z_pliku(cls, plik: str | Path) -> KonfiguracjaOceny:
        return cls.model_validate(yaml.safe_load(Path(plik).read_text(encoding="utf-8")))

    def na_skale(self, sciezka: Sciezka, poziom_modelu: int) -> int:
        return self.mapowanie_pierwsza.wartosci[poziom_modelu] if sciezka == "pierwsza" else poziom_modelu


# ---------------------------------------------------------------- dane wejściowe


class Przyklad(BaseModel):
    """Przykład zachowania według instrukcji modelu (A5): sytuacja – działanie – rezultat."""

    sytuacja: str = Field(min_length=1, max_length=2000)
    dzialanie: str = Field(min_length=1, max_length=2000)
    rezultat: str = Field(min_length=1, max_length=2000)
    powtarzalnosc: Literal["JEDNORAZOWE", "KILKAKROTNE", "REGULARNE"] | None = None
    zlozonosc: Literal["NISKA", "SREDNIA", "WYSOKA"] | None = None
    uprawnienia: str | None = Field(default=None, max_length=1000)

    @field_validator("sytuacja", "dzialanie", "rezultat")
    @classmethod
    def _niepuste(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("pole nie może być puste")
        return v.strip()

    def jako_tekst(self) -> str:
        return f"Sytuacja: {self.sytuacja} Działanie: {self.dzialanie} Rezultat: {self.rezultat}"


class OcenaWskaznika(BaseModel):
    poziom: Literal[1, 3, 5, 7, 9] | None = None
    brak_podstaw: bool = False
    przyklady: list[Przyklad] = Field(default_factory=list)
    uwagi: str | None = Field(default=None, max_length=2000)
    """Uwagi przełożonego z rozmowy przy wskaźniku (zamiast pełnego przykładu)."""

    @model_validator(mode="after")
    def _wykluczanie(self) -> OcenaWskaznika:
        if self.poziom is not None and self.brak_podstaw:
            raise ValueError("Wskaźnik ma albo poziom, albo „brak podstaw do oceny”, nie oba.")
        if self.poziom is None and not self.brak_podstaw:
            raise ValueError("Podaj poziom albo zaznacz „brak podstaw do oceny” (null usuwa ocenę).")
        return self


class ZapisWskaznikow(BaseModel):
    wskazniki: dict[str, OcenaWskaznika | None]


class NowaDecyzja(BaseModel):
    punkty: int
    uzasadnienie: str | None = Field(default=None, max_length=4000)


class ZapisDecyzji(BaseModel):
    decyzje: dict[str, NowaDecyzja | None]


class Decyzja(BaseModel):
    punkty: int
    uzasadnienie: str | None
    zgodna_z_sugestia: bool | None
    """None, gdy sugestii nie było (niewystarczające dane)."""
    zapisal: str
    zapisano: datetime


def aktualne_decyzje(wybor: WyborKroku2, decyzje: dict[str, Decyzja]) -> dict[str, Decyzja]:
    """Zwróć decyzje zapisane dla bieżącego wyboru kryteriów."""
    return {
        k.kompetencja_id: d
        for k in wybor.kryteria
        if (d := decyzje.get(k.kompetencja_id)) is not None and d.zapisano >= wybor.zapisano
    }


# ---------------------------------------------------------------- odpowiedź


class Sugestia(BaseModel):
    status: Literal["POZIOM", "REMIS", "NIEWYSTARCZAJACE_DANE"]
    poziom_modelu: int | None = None
    remis: list[int] | None = None
    punkty: int | None = None
    punkty_remisu: list[int] | None = None
    rozklad: dict[str, int]
    oceniono: int
    wybrano: int
    opis: str
    metodyka: str


class OpisPoziomuWidok(BaseModel):
    poziom: int
    etykieta: str
    opis: str


class SamoocenaWskaznika(BaseModel):
    """Odpowiedź pracownika przy wskaźniku (#8); nie wchodzi do sugestii ani do oceny."""

    poziom: int | None
    brak_zdania: bool
    przyklad: Przyklad | None


class WskaznikOceny(BaseModel):
    wskaznik_id: str
    nazwa: str
    poziomy: list[OpisPoziomuWidok]
    ocena: OcenaWskaznika | None
    ostrzezenia: list[str]
    samoocena: SamoocenaWskaznika | None = None
    """Tylko dla przełożonego i tylko po przekazaniu samooceny (#8)."""
    rozbieznosc: bool | None = None
    """|samoocena − ocena przełożonego| ≥ próg z ``samoocena.yaml``; None, gdy brak obu poziomów."""


class KryteriumOceny(BaseModel):
    kompetencja_id: str
    nazwa: str
    rodzaj: Literal["OBOWIAZKOWE", "DODATKOWE"]
    wskazniki: list[WskaznikOceny]
    sugestia: Sugestia
    decyzja: Decyzja | None


class Kompletnosc(BaseModel):
    wskazniki_ocenione: int
    wskazniki_wybrane: int
    kryteria_z_decyzja: int
    kryteria: int

    @property
    def wszystkie_decyzje(self) -> bool:
        return self.kryteria > 0 and self.kryteria_z_decyzja == self.kryteria


class WskaznikDlaRozwoju(BaseModel):
    """Format wejścia ``/api/rozwoj/propozycje`` (#36)."""

    kompetencja: str
    wskaznik: str
    wskaznik_id: str
    poziom: int | None
    przyklady: list[str]


class SkalaWidok(BaseModel):
    punkty: list[int]
    etykiety: dict[int, str]
    adnotacje: list[SourceRef]


Tekst = Annotated[str, Field(max_length=4000)]


class ZapisRozmowy(BaseModel):
    """Rozmowa oceniająca (rozp. 2016 § 10): notatki tematów, szkic informacji zwrotnej i data.
    Data trafia do części II arkusza, notatka o rozwoju podpowiada wnioski (§ 11 ust. 1 pkt 5)."""

    data: date | None = None
    notatki: dict[Literal["obowiazki", "sprawozdanie", "cele", "rozwoj"], Tekst] = Field(default_factory=dict)
    mocne_strony: Tekst | None = None
    obszary_rozwoju: Tekst | None = None


class StanOceny(BaseModel):
    samoocena_status: Literal["brak", "szkic", "przekazana"] | None = None
    """Status samooceny (#8), tylko dla przełożonego; treść przy wskaźnikach po przekazaniu."""
    proces_id: int
    sciezka: Sciezka
    arkusz: str
    skala: SkalaWidok
    metodyka: Metodyka
    mapowanie: Mapowanie | None
    instrukcja: list[Instrukcja]
    kryteria: list[KryteriumOceny]
    kompletnosc: Kompletnosc
    ostrzezenia: list[str]
    dla_rozwoju: list[WskaznikDlaRozwoju]
    rozmowa: ZapisRozmowy | None = None
    """Zapis rozmowy oceniającej; ``None``, dopóki przełożony nic nie zapisał."""


# ---------------------------------------------------------------- logika


def sugestia(
    oceny: list[OcenaWskaznika | None], sciezka: Sciezka, konf: KonfiguracjaOceny
) -> Sugestia:
    """Sugerowany poziom kryterium z ocen jego wybranych wskaźników (``None`` = nieoceniony)."""
    m = konf.metodyka
    poziomy = sorted(o.poziom for o in oceny if o is not None and o.poziom is not None)
    brak = sum(1 for o in oceny if o is not None and o.brak_podstaw)
    rozklad = {str(p): poziomy.count(p) for p in POZIOMY_MODELU}
    rozklad["brak_podstaw"] = brak
    rozklad["nieocenione"] = sum(1 for o in oceny if o is None)
    wspolne = dict(rozklad=rozklad, oceniono=len(poziomy), wybrano=len(oceny), metodyka=m.etykieta)

    wymagane = max(1, math.ceil(len(oceny) * m.minimalny_udzial_ocenionych))
    if len(poziomy) < wymagane:
        return Sugestia(
            status="NIEWYSTARCZAJACE_DANE",
            opis=f"Niewystarczające dane: oceniono {len(poziomy)} z {len(oceny)} wybranych "
            f"wskaźników, potrzeba co najmniej {wymagane}.",
            **wspolne,
        )

    n = len(poziomy)
    lista = ", ".join(map(str, poziomy))
    if n % 2 == 1 or poziomy[n // 2 - 1] == poziomy[n // 2]:
        mediana = poziomy[n // 2]
        punkty = konf.na_skale(sciezka, mediana)
        przeliczenie = f" → {punkty} pkt (mapowanie 5→3)" if sciezka == "pierwsza" else f" → {punkty} pkt"
        return Sugestia(
            status="POZIOM",
            poziom_modelu=mediana,
            punkty=punkty,
            opis=f"Mediana z {n} ocenionych wskaźników ({lista}) = {mediana}{przeliczenie}.",
            **wspolne,
        )

    remis = [poziomy[n // 2 - 1], poziomy[n // 2]]
    punkty_remisu = sorted({konf.na_skale(sciezka, p) for p in remis})
    if len(punkty_remisu) == 1:  # pierwsza ocena: oba środkowe dają te same punkty (np. 1 i 3 → 3)
        return Sugestia(
            status="POZIOM",
            remis=remis,
            punkty=punkty_remisu[0],
            opis=f"Wartości środkowe {remis[0]} i {remis[1]} z ({lista}) po mapowaniu 5→3 dają "
            f"te same {punkty_remisu[0]} pkt.",
            **wspolne,
        )
    return Sugestia(
        status="REMIS",
        remis=remis,
        punkty_remisu=punkty_remisu,
        opis=f"Remis: wartości środkowe z ({lista}) to {remis[0]} i {remis[1]} "
        f"({punkty_remisu[0]} albo {punkty_remisu[1]} pkt). Wybór należy do przełożonego.",
        **wspolne,
    )


def zgodna(punkty: int, s: Sugestia) -> bool | None:
    if s.status == "POZIOM":
        return punkty == s.punkty
    if s.status == "REMIS":
        return punkty in (s.punkty_remisu or [])
    return None


def ostrzezenia_wskaznika(o: OcenaWskaznika | None, konf: KonfiguracjaOceny) -> list[str]:
    if o is None or o.poziom is None:
        return []
    if o.poziom != konf.poziom_oczekiwan and not o.przyklady and not (o.uwagi or "").strip():
        return [konf.przyklady.ostrzezenie_bez_przykladu]
    return []


def zbuduj_stan(
    proces_id: int,
    sciezka: Sciezka,
    arkusz: str,
    wybor: WyborKroku2,
    oceny: dict[str, OcenaWskaznika],
    decyzje: dict[str, Decyzja],
    model: ModelKompetencji,
    konf: KonfiguracjaOceny,
) -> StanOceny:
    # Decyzje sprzed ponownego zapisu kryteriów nie liczą się (#114).
    decyzje = aktualne_decyzje(wybor, decyzje)
    kryteria: list[KryteriumOceny] = []
    ostrzezenia: list[str] = []
    dla_rozwoju: list[WskaznikDlaRozwoju] = []
    ocenione = wybrane = 0
    for k in wybor.kryteria:
        komp = model.kompetencja(k.kompetencja_id)
        po_id = {w.id: w for w in komp.wskazniki} if komp else {}
        wskazniki = []
        for w in k.wskazniki:
            o = oceny.get(w.id)
            ostrz = ostrzezenia_wskaznika(o, konf)
            ostrzezenia += [f"{k.nazwa} / {w.nazwa}: {t}" for t in ostrz]
            mw = po_id.get(w.id)
            wskazniki.append(
                WskaznikOceny(
                    wskaznik_id=w.id,
                    nazwa=w.nazwa,
                    poziomy=[
                        OpisPoziomuWidok(poziom=p.poziom, etykieta=p.etykieta, opis=p.opis)
                        for p in (mw.poziomy if mw else [])
                    ],
                    ocena=o,
                    ostrzezenia=ostrz,
                )
            )
            wybrane += 1
            ocenione += o is not None
            if o is not None:
                dla_rozwoju.append(
                    WskaznikDlaRozwoju(
                        kompetencja=k.nazwa,
                        wskaznik=w.nazwa,
                        wskaznik_id=w.id,
                        poziom=o.poziom,
                        # Pole „Przykład z okresu” przy wskaźniku zapisuje się jako uwagi (#72 pkt 7).
                        przyklady=[p.jako_tekst() for p in o.przyklady] or ([o.uwagi] if o.uwagi else []),
                    )
                )
        kryteria.append(
            KryteriumOceny(
                kompetencja_id=k.kompetencja_id,
                nazwa=k.nazwa,
                rodzaj=k.rodzaj,
                wskazniki=wskazniki,
                sugestia=sugestia([oceny.get(w.id) for w in k.wskazniki], sciezka, konf),
                decyzja=decyzje.get(k.kompetencja_id),
            )
        )
    skala = konf.skale[sciezka]
    return StanOceny(
        proces_id=proces_id,
        sciezka=sciezka,
        arkusz=arkusz,
        skala=SkalaWidok(punkty=skala.punkty, etykiety=skala.etykiety, adnotacje=skala.adnotacje),
        metodyka=konf.metodyka,
        mapowanie=konf.mapowanie_pierwsza if sciezka == "pierwsza" else None,
        instrukcja=model.instrukcja,
        kryteria=kryteria,
        kompletnosc=Kompletnosc(
            wskazniki_ocenione=ocenione,
            wskazniki_wybrane=wybrane,
            kryteria_z_decyzja=sum(1 for k in kryteria if k.decyzja is not None),
            kryteria=len(kryteria),
        ),
        ostrzezenia=ostrzezenia,
        dla_rozwoju=dla_rozwoju,
    )


class BladOceny(ValueError):
    pass


def scal_oceny(
    obecne: dict[str, OcenaWskaznika], zapis: ZapisWskaznikow, wybor: WyborKroku2
) -> dict[str, OcenaWskaznika]:
    dozwolone = {w.id for k in wybor.kryteria for w in k.wskazniki}
    if obce := sorted(set(zapis.wskazniki) - dozwolone):
        raise BladOceny([f"Wskaźnik „{w}” nie jest wybrany w kroku 2." for w in obce])
    wynik = dict(obecne)
    for w_id, o in zapis.wskazniki.items():
        if o is None:
            wynik.pop(w_id, None)
        else:
            wynik[w_id] = o
    return wynik


def scal_decyzje(
    obecne: dict[str, Decyzja],
    zapis: ZapisDecyzji,
    stan: StanOceny,
    konf: KonfiguracjaOceny,
    zapisal: str,
    zapisano: datetime,
) -> dict[str, Decyzja]:
    po_id = {k.kompetencja_id: k for k in stan.kryteria}
    skala = konf.skale[stan.sciezka].punkty
    bledy: list[str] = []
    wynik = dict(obecne)
    for k_id, d in zapis.decyzje.items():
        k = po_id.get(k_id)
        if k is None:
            bledy.append(f"Kryterium „{k_id}” nie jest wybrane w kroku 2.")
            continue
        if d is None:
            wynik.pop(k_id, None)
            continue
        if d.punkty not in skala:
            bledy.append(f"{k.nazwa}: {d.punkty} pkt spoza skali {skala}.")
            continue
        uzasadnienie = (d.uzasadnienie or "").strip() or None
        z = zgodna(d.punkty, k.sugestia)
        wynik[k_id] = Decyzja(
            punkty=d.punkty, uzasadnienie=uzasadnienie, zgodna_z_sugestia=z, zapisal=zapisal, zapisano=zapisano
        )
    if bledy:
        raise BladOceny(bledy)
    return wynik
