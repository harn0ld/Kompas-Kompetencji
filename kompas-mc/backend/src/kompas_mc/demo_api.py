"""Demo: „Rozpocznij od początku” (#186). Osoba demo wraca do pierwszego etapu oceny.

Przycisk dostają tylko osoby z ``demo_od_poczatku`` w ``qnt.yaml``: Anna Zielińska-Demo (ocena okresowa)
i Zofia Szymańska-Demo (pierwsza ocena). Reset kasuje z bazy wszystko, co aplikacja zapisała o tej osobie:
procesy oceny (kroki, ocenę, rozmowę, wynik, zakończenie), samoocenę, rejestr EZD, przypomnienia, cele
i notatki, a także wpisy dziennika zmian tych zasobów, żeby nowy proces nie dziedziczył historii.
Rejestr operacji zostaje: jest tylko do dopisywania i odnotowuje sam reset.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Uzytkownik
from pydantic import BaseModel

from .qnt import MockQnt
from .rejestr import ustaw_osobe


class WynikResetu(BaseModel):
    osoba_id: str
    sciezka: str
    usuniete_procesy: int
    usuniete_cele: int
    usuniete_notatki: int


def _tabela_istnieje(baza, nazwa: str) -> bool:
    return baza.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (nazwa,)).fetchone() is not None


def wyczysc_osobe(baza, osoba_id: str) -> tuple[int, int, int]:
    """Usuwa dane oceny osoby; zwraca liczbę usuniętych procesów, celów i notatek. Jedna transakcja."""
    with baza:
        procesy = [w[0] for w in baza.execute("SELECT id FROM procesy WHERE osoba_id = ?", (osoba_id,))]
        cele = [w[0] for w in baza.execute("SELECT id FROM cele WHERE osoba_id = ?", (osoba_id,))]
        znaki = ", ".join("?" * len(procesy))
        if procesy:
            for tabela in ("samoocena_pozycje", "samoocena", "rejestr_ezd", "skrzynka_nadawcza"):
                if _tabela_istnieje(baza, tabela):
                    baza.execute(f"DELETE FROM {tabela} WHERE proces_id IN ({znaki})", procesy)
            baza.execute(f"DELETE FROM procesy WHERE id IN ({znaki})", procesy)
        baza.execute("DELETE FROM cele WHERE osoba_id = ?", (osoba_id,))
        notatki = baza.execute("DELETE FROM notatki WHERE osoba_id = ?", (osoba_id,)).rowcount
        # Dziennik zmian (nie rejestr operacji): identyfikatory w SQLite mogą wrócić po usunięciu wiersza,
        # więc nowy proces o tym samym id nie może pokazać historii starego.
        if _tabela_istnieje(baza, "dziennik"):
            for zasob, ids in (("proces", procesy), ("samoocena", procesy), ("cel", cele)):
                if ids:
                    baza.execute(
                        f"DELETE FROM dziennik WHERE zasob = ? AND zasob_id IN ({', '.join('?' * len(ids))})",
                        [zasob, *map(str, ids)],
                    )
    return len(procesy), len(cele), notatki


def router(auth: Autoryzacja, qnt: MockQnt) -> APIRouter:
    r = APIRouter(prefix="/api/demo", tags=["demo"])

    @r.post("/pracownicy/{osoba_id}/od-poczatku")
    def od_poczatku(osoba_id: str, request: Request, uz: Uzytkownik = auth.wymagaj("ocena.prowadz")) -> WynikResetu:
        """Kasuje dane oceny osoby demo; ocena zaczyna się od pierwszego etapu.

        404: nie ma osoby w QNT. 403: osoba poza zakresem użytkownika albo bez ``demo_od_poczatku``.
        """
        ustaw_osobe(request, osoba_id)
        p = qnt.pracownik(osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", p.model_dump(), "ocena.prowadz")
        if p.demo_od_poczatku is None:
            raise HTTPException(403, "Od początku można zacząć tylko ocenę osoby demo")
        procesy, cele, notatki = wyczysc_osobe(request.app.state.baza, osoba_id)
        return WynikResetu(
            osoba_id=osoba_id, sciezka=p.demo_od_poczatku,
            usuniete_procesy=procesy, usuniete_cele=cele, usuniete_notatki=notatki,
        )

    return r
