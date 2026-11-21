"""API Kompasu Kompetencji."""

from __future__ import annotations

from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, Request
from kompas_core.auth import Autoryzacja, Dziennik, KonfiguracjaRol
from kompas_core.llm import DziennikJsonl
from pydantic import BaseModel, Field

from .arkusz_api import router as router_arkusza
from .arkusze import WzoryArkuszy
from .asystent import Asystent, KonfiguracjaAsystenta, OdpowiedzAsystenta, Sciezka
from .baza import polacz
from .braki import PanelBrakow, zbuduj_panel
from .kompetencje import odczytaj as odczytaj_model
from .korpus_mc import zaladuj
from .cykl import router as router_cyklu
from .hr import terminy_z_regul
from .hr_api import router as router_hr
from .hr_api import router_terminow
from .cele import KonfiguracjaCelow
from .cele_api import router as router_celow
from .samoocena import KonfiguracjaSamooceny
from .samoocena_api import router as router_samooceny
from .krok1 import KonfiguracjaKroku1, proponuj_sciezke
from .krok2 import KonfiguracjaKroku2
from .krok2_api import StanKroku2
from .krok2_api import router as router_kroku2
from .ocena import KonfiguracjaOceny
from .metodyka import RejestrMetodyk
from .metodyka_api import router as router_metodyki
from .ocena_api import router as router_oceny
from .osp import KatalogOsp
from .pierwsza_ocena_api import router as router_pierwszej
from .pracownicy import router as router_pracownikow
from .procesy import router as router_procesow
from .qnt import MockQnt
from .rozmowa import KonfiguracjaRozmowy
from .rozmowa_api import router as router_rozmowy
from .rozwoj_api import router as router_wnioskow
from .rozwoj import DaneRozwoju, KonfiguracjaRozwoju, WynikRozwoju, zaproponuj
from .terminy_okresowej import KonfiguracjaTerminow
from .terminy_pierwszej import KonfiguracjaTerminowPierwszej
from .ustawienia import Ustawienia
from .wynik_okresowy import KonfiguracjaWynikuOkresowego
from .wynik_okresowy_api import SerwisWynikuOkresowego, router as router_wyniku_okresowego
from .wynik_pierwszej import KonfiguracjaWynikuPierwszej


class PytanieAsystenta(BaseModel):
    pytanie: str = Field(min_length=1, max_length=1000)
    sciezka: Sciezka | None = None


def utworz_aplikacje(ustawienia: Ustawienia | None = None) -> FastAPI:
    ust = ustawienia or Ustawienia.ze_srodowiska()

    @asynccontextmanager
    async def cykl(app: FastAPI):
        app.state.ustawienia = ust
        app.state.baza = polacz(ust.baza)
        app.state.dziennik = Dziennik(ust.baza)
        app.state.korpus = korpus = zaladuj(ust.manifest)
        katalog.wczytaj(korpus)
        krok2.model = odczytaj_model(korpus)
        konf_krok2.sprawdz(krok2.model)
        krok2.zal1 = {
            doc: [
                f
                for f in korpus.korpus.fragmenty
                if f.doc_id == doc and (f.lokalizator or "").startswith("zał. 1")
            ]
            for doc in set(konf_krok2.podstawa_wskaznikow.values())
        }
        app.state.asystent = Asystent(
            app.state.korpus,
            KonfiguracjaAsystenta.z_pliku(ust.konfiguracja_asystenta),
            DziennikJsonl(ust.log_llm),
        )
        app.state.panel = zbuduj_panel(ust.braki, app.state.korpus)
        app.state.rozwoj = KonfiguracjaRozwoju.z_pliku(ust.rozwoj)
        app.state.samoocena = KonfiguracjaSamooceny.z_pliku(ust.samoocena)
        app.state.cele = KonfiguracjaCelow.z_pliku(ust.cele)
        app.state.metodyki = RejestrMetodyk(app.state.baza, KonfiguracjaOceny.z_pliku(ust.ocena))
        app.state.terminy = terminy_z_regul(konf_terminow_okresowej, konf_terminow_pierwszej, app.state.baza)
        yield
        app.state.baza.close()

    app = FastAPI(title="Kompas Kompetencji", lifespan=cykl)
    role = yaml.safe_load(ust.role.read_text(encoding="utf-8"))
    auth = Autoryzacja(KonfiguracjaRol.model_validate(role))
    app.include_router(auth.router(), prefix="/api", tags=["logowanie"])
    qnt = MockQnt.z_pliku(ust.qnt)
    katalog = KatalogOsp()
    app.include_router(router_pracownikow(auth, qnt))
    konf_krok1 = KonfiguracjaKroku1.z_pliku(ust.krok1)
    app.include_router(router_procesow(auth, qnt, katalog, konf_krok1))
    krok2 = StanKroku2()
    konf_krok2 = KonfiguracjaKroku2.z_pliku(ust.krok2)
    app.include_router(router_kroku2(auth, qnt, katalog, konf_krok2, krok2))
    app.include_router(router_oceny(auth, qnt, krok2))
    app.include_router(router_metodyki(auth))
    app.include_router(router_rozmowy(auth, qnt, krok2, KonfiguracjaRozmowy.z_pliku(ust.rozmowa)))
    skale = KonfiguracjaOceny.z_pliku(ust.ocena).skale
    konf_terminow_okresowej = KonfiguracjaTerminow.z_pliku(ust.terminy_okresowej)
    konf_terminow_pierwszej = KonfiguracjaTerminowPierwszej.z_pliku(ust.terminy_pierwszej)
    serwis_wyniku = SerwisWynikuOkresowego(
        KonfiguracjaWynikuOkresowego.z_pliku(ust.wynik_okresowy),
        konf_terminow_okresowej, skale["okresowa"].punkty,
    )
    app.include_router(router_wyniku_okresowego(auth, qnt, serwis_wyniku))
    wzory = WzoryArkuszy.z_pliku(ust.wzory_arkuszy)
    app.include_router(router_arkusza(
        auth, qnt, serwis_wyniku, konf_krok2, wzory,
    ))
    pierwsza, czytaj_pierwsza = router_pierwszej(
        auth, qnt, KonfiguracjaWynikuPierwszej.z_pliku(ust.wynik_pierwszej),
        konf_terminow_pierwszej, konf_krok2, wzory, skale["pierwsza"].punkty,
    )
    app.include_router(pierwsza)
    app.include_router(router_wnioskow(auth, qnt, krok2, serwis_wyniku, czytaj_pierwsza))
    app.include_router(router_hr(auth, qnt))
    app.include_router(router_terminow(auth, qnt))
    app.include_router(router_cyklu(
        auth, qnt, konf_terminow_okresowej, konf_terminow_pierwszej,
        lambda p: proponuj_sciezke(p, konf_krok1).proponowana,
    ))
    app.include_router(router_samooceny(auth, qnt, krok2))
    app.include_router(router_celow(auth, qnt, krok2))

    @app.get("/api/zdrowie")
    def zdrowie(request: Request) -> dict:
        k = request.app.state.korpus
        return {
            "wersja": "mc-bdg",
            "port": request.app.state.ustawienia.port,
            "dokumenty": len(k.dokumenty),
            "fragmenty": len(k.korpus.fragmenty),
        }

    @app.get("/api/zrodla")
    def zrodla(request: Request) -> dict:
        k = request.app.state.korpus
        raport = {w.doc_id: w for w in k.korpus.raport}
        return {
            "dokumenty": [
                {
                    "doc_id": d.doc_id,
                    "nazwa": d.nazwa,
                    "plik": d.plik.name,
                    "sciezka": d.sciezka,
                    "kategoria": d.kategoria.value,
                    "w_asystencie": d.asystent,
                    "status": raport[d.doc_id].status.value,
                    "fragmenty": len(raport[d.doc_id].fragmenty),
                    "komunikat": raport[d.doc_id].komunikat,
                }
                for d in k.dokumenty.values()
            ],
            "duplikaty": [
                {
                    "plik": d.plik.name,
                    "duplikat_z": d.duplikat_z,
                    "pokrycie": d.pokrycie,
                    "potwierdzony": d.potwierdzony,
                    "opis": d.opis,
                }
                for d in k.duplikaty
            ],
            "pominiete": [{"plik": p.plik.name, "powod": p.powod} for p in k.pominiete],
        }

    @app.get("/api/braki")
    def braki(request: Request, _uz=auth.wymagaj("zrodla.panel")) -> PanelBrakow:
        """Braki, rozbieżności, duplikaty i pytania do mentorów MC (HR/administrator)."""
        return request.app.state.panel

    @app.post("/api/rozwoj/propozycje")
    def propozycje_rozwoju(
        request: Request, dane: DaneRozwoju, _uz=auth.wymagaj("rozwoj.propozycje")
    ) -> WynikRozwoju:
        """Propozycje obszarów i form rozwoju (krok 8). Treści wniosków nie generuje."""
        return zaproponuj(dane, request.app.state.rozwoj)

    @app.post("/api/asystent")
    def asystent(request: Request, body: PytanieAsystenta) -> OdpowiedzAsystenta:
        return request.app.state.asystent.odpowiedz(body.pytanie, body.sciezka)

    return app


app = utworz_aplikacje()
