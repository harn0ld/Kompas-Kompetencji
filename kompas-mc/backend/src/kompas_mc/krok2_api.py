"""API kroku 2 (#30): model kompetencji, propozycja kryteriów i wskaźników, zapis wyboru."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Dziennik, Uzytkownik
from kompas_core.zrodla import Fragment

from .kompetencje import ModelKompetencji
from .krok2 import (
    ZapisZapoznania,
    BladWyboru,
    KonfiguracjaKroku2,
    PropozycjaKroku2,
    ZapisKroku2,
    zaproponuj,
    zatwierdz,
)
from .osp import KatalogOsp
from .procesy import ProcesOceny, dzien_urzedowy, wczytaj_proces
from .qnt import MockQnt


class StanKroku2:
    """Model i fragmenty zał. 1 powstają z korpusu przy starcie aplikacji."""

    model: ModelKompetencji
    zal1: dict[str, list[Fragment]]


def router(
    auth: Autoryzacja, qnt: MockQnt, katalog: KatalogOsp, konf: KonfiguracjaKroku2, stan: StanKroku2
) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["krok 2: kryteria i wskaźniki"])

    @r.get("/model-kompetencji")
    def model(_uz: Uzytkownik = auth.wymagaj("ocena.czytaj")) -> ModelKompetencji:
        """14 kompetencji, 49 wskaźników, 5 poziomów i instrukcja z Model_kompetencji.xlsx."""
        return stan.model

    def proces_dostepny(request: Request, proces_id: int, uz: Uzytkownik, akcja: str) -> ProcesOceny:
        proces = wczytaj_proces(request.app.state.baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        p = qnt.pracownik(proces.osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", p.model_dump(), akcja)
        return proces

    def propozycja(proces: ProcesOceny) -> PropozycjaKroku2:
        osp = katalog.po_symbolu(proces.krok1.osp.symbol) if proces.krok1.osp else None
        doc = konf.podstawa_wskaznikow[proces.sciezka]
        return zaproponuj(
            proces.id,
            proces.sciezka,
            proces.arkusz,
            osp,
            stan.model,
            stan.zal1[doc],
            konf,
            proces.krok2,
        )

    @r.get("/procesy/{proces_id}/krok2")
    def krok2(
        proces_id: int, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.czytaj")
    ) -> PropozycjaKroku2:
        """Kryteria obowiązkowe według arkusza, propozycje dodatkowych (najwyżej 3, w pierwszej
        ocenie 0) i wskaźniki z zadaniami z OSP, które je uzasadniają."""
        return propozycja(proces_dostepny(request, proces_id, uz, "ocena.czytaj"))

    @r.put("/procesy/{proces_id}/krok2")
    def zapisz(
        proces_id: int,
        body: ZapisKroku2,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> ProcesOceny:
        """Przełożony zatwierdza kryteria dodatkowe i wskaźniki. 422 z listą problemów przy
        błędnym wyborze; 409, gdy proces nie jest w toku."""
        proces = proces_dostepny(request, proces_id, uz, "ocena.prowadz")
        if proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")
        try:
            wybor = zatwierdz(
                body, proces.sciezka, proces.arkusz, stan.model, konf, uz.login, datetime.now(UTC)
            )
        except BladWyboru as e:
            raise HTTPException(422, {"komunikat": "Wybór kryteriów jest niepoprawny.", "bledy": e.args[0]})

        baza = request.app.state.baza
        with baza:
            # Nowy wybór unieważnia decyzje sprzed niego (aktualne_decyzje), więc proces wraca
            # najwyżej do oceny wskaźników (krok 3), które zostają (#114).
            zmieniono = baza.execute(
                "UPDATE procesy SET krok2 = ?, krok = MIN(MAX(krok, 2), 3) WHERE id = ? AND status = 'W_TOKU'",
                (wybor.model_dump_json(), proces.id),
            ).rowcount
        if not zmieniono:
            raise HTTPException(409, "Proces nie jest w toku")
        po = wczytaj_proces(baza, proces.id)
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(
            uz.login,
            "proces",
            str(proces.id),
            {"krok": proces.krok, "krok2": _bez_czasu(proces.krok2)},
            {"krok": po.krok, "krok2": _bez_czasu(po.krok2)},
            konf.wersja,
        )
        return po

    @r.put("/procesy/{proces_id}/krok2/zapoznanie")
    def zapoznanie(
        proces_id: int,
        body: ZapisZapoznania,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> ProcesOceny:
        """Zakończenie części I: data rozmowy na początku okresu i zapoznania ocenianego z kryteriami
        (rozp. 2016 § 5 ust. 1, § 6 ust. 2). Na końcu okresu przełożony przepisuje ją z podpisanej części I.
        409 przed zapisem kryteriów albo poza toku; 422, gdy data jest z przyszłości albo sprzed początku
        okresu (poprzednia ocena na piśmie albo zatrudnienie, § 7 pkt 1)."""
        proces = proces_dostepny(request, proces_id, uz, "ocena.prowadz")
        if proces.status != "W_TOKU":
            raise HTTPException(409, "Proces nie jest w toku")
        if proces.krok2 is None:
            raise HTTPException(409, "Najpierw zatwierdź kryteria (krok 2).")
        p = qnt.pracownik(proces.osoba_id)
        od = (p.ostatnia_ocena_okresowa.data if p.ostatnia_ocena_okresowa else p.data_zatrudnienia) if p else None
        if body.data > dzien_urzedowy(datetime.now(UTC)) or (od and body.data < od):
            raise HTTPException(
                422, f"Data zapoznania z kryteriami musi przypadać od {od:%d.%m.%Y} (początek okresu oceny) do dziś."
                if od else "Data zapoznania z kryteriami nie może być z przyszłości.",
            )
        baza = request.app.state.baza
        przed = proces.krok2.zapoznanie
        with baza:
            # json_set zmienia tylko datę, więc równoległy zapis kryteriów nie przepada (#114).
            zmieniono = baza.execute(
                "UPDATE procesy SET krok2 = json_set(krok2, '$.zapoznanie', ?)"
                " WHERE id = ? AND status = 'W_TOKU' AND krok2 IS NOT NULL",
                (body.data.isoformat(), proces.id),
            ).rowcount
        if not zmieniono:
            raise HTTPException(409, "Proces nie jest w toku")
        dziennik: Dziennik = request.app.state.dziennik
        dziennik.zapisz(
            uz.login, "proces", str(proces.id),
            {"zapoznanie": przed.isoformat() if przed else None}, {"zapoznanie": body.data.isoformat()}, konf.wersja,
        )
        return wczytaj_proces(baza, proces.id)

    return r


def _bez_czasu(wybor) -> list | None:
    if wybor is None:
        return None
    return json.loads(wybor.model_dump_json(include={"kryteria"}))["kryteria"]
