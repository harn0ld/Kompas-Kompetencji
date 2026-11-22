"""API asystenta rozmowy (#35, krok 6): plan rozmowy oceniającej jako sugestia."""

from __future__ import annotations

import copy
import json

from fastapi import APIRouter, HTTPException, Request
from kompas_core.auth import Autoryzacja, Uzytkownik
from kompas_core.llm import BrakOdpowiedzi, Tryb, Zapytanie, wywolaj
from kompas_core.zrodla import Fragment, Kategoria
from pydantic import BaseModel, Field

from .asystent import Asystent, CytatAsystenta, OdpowiedzAsystenta, proponuje_ocene
from .krok2_api import StanKroku2
from .metodyka import RejestrMetodyk
from .ocena import zbuduj_stan
from .ocena_api import _wczytaj_dane
from .procesy import wczytaj_proces
from .pseudonimizacja import Pseudonimizator
from .qnt import MockQnt
from .rozmowa import KonfiguracjaRozmowy, KontekstRozmowy, PlanRozmowy, przygotuj


class PytanieCzatu(BaseModel):
    pytanie: str = Field(min_length=1, max_length=1000)


class OdpowiedzCzatu(OdpowiedzAsystenta):
    oznaczenie_sugestii: str
    kwestie: list[str] = []
    """Przygotowanie do rozmowy (#178): sprawy do omówienia z pracownikiem, każda oparta na cytowanym fragmencie."""
    argumenty: list[str] = []
    """Obserwacje z przebiegu tej oceny, które przełożony może przytoczyć w uzasadnieniu."""


# Czat przygotowania (#178, zadanie MC: „wskazywanie kwestii wymagających omówienia czy pomoc w uporządkowaniu
# argumentów uzasadniających ocenę”). Dane tej oceny są cytowalnymi fragmentami „ocena#…” (wskaźnik, wybrany opis
# zachowania, przykłady, uwagi – lista dane_dla_modelu w rozmowa.yaml; bez punktów i bez danych identyfikujących).
POLECENIE_PRZYGOTOWANIA = """Przygotuj przełożonego do rozmowy oceniającej: zwięźle, jasno, tylko meritum.
Fragmenty o ID zaczynającym się od "ocena#" to dane tej oceny (wskaźnik, zachowanie wybrane przez przełożonego,
przykłady z okresu, uwagi); pozostałe to przepisy i poradniki. Korzystaj wyłącznie z fragmentów.
W polu "tresc" zwróć tekst z obiektem JSON: {"kwestie": ["..."], "argumenty": ["..."]}
"kwestie": najwyżej 3 sprawy do omówienia, wynikające wprost z danych oceny: czego brakuje do oczekiwanego
zachowania, gdzie nie ma przykładu albo podstaw do oceny. "argumenty": najwyżej 3 obserwacje z fragmentów
"ocena#…", które przełożony może przytoczyć. Każdy punkt to jedno krótkie zdanie (do 20 słów) o tym, o co pytał
przełożony. Bez ogólnych porad, szkoleń, planów rozwoju i powtórzeń. Fragment, na którym opiera się punkt,
zacytuj w "cytaty". Liczby i daty przepisuj wyłącznie z cytowanych fragmentów.
Nie proponuj punktów, poziomu ani wyniku oceny i nie wartościuj osoby: decyzja należy do przełożonego."""
OPERACJA_PRZYGOTOWANIA = "asystent_przygotowanie"
MAKS_PUNKTOW = 3  # Karol 22.11 09:16: zwięźle, meritum
# Ogólne pytanie niesie dane wszystkich ocenionych wskaźników: model odpowiada w 12–15 s, czasem ponad 30 s
# (serwer 22.11). ponytail: stały limit dla tej operacji; osobne pole w asystent.yaml, gdy będzie potrzeba.
LIMIT_PRZYGOTOWANIA_S = 60


def fragmenty_oceny(stan, pseudo: Pseudonimizator, osoba_id: str) -> list[Fragment]:
    """Ocenione wskaźniki jako fragmenty do cytowania; bez punktów i etykiet poziomów, teksty po pseudonimizacji."""
    wynik: list[Fragment] = []
    for k in stan.kryteria:
        for w in k.wskazniki:
            o = w.ocena
            if o is None:
                continue
            kryterium = k.nazwa.capitalize()  # w modelu kompetencji wersaliki; na ekranie zdaniowo
            czesci = [f"Kryterium: {kryterium}. Wskaźnik: {w.nazwa}."]
            opis = next((p.opis for p in w.poziomy if p.poziom == o.poziom), None)
            czesci.append(f"Zachowanie wybrane przez przełożonego: {opis}" if opis else "Przełożony zaznaczył brak podstaw do oceny.")
            czesci += [f"Przykład z okresu: {p.sytuacja} – {p.dzialanie} – {p.rezultat}" for p in o.przyklady]
            if o.uwagi:
                czesci.append(f"Uwagi przełożonego: {o.uwagi}")
            wynik.append(Fragment(
                id=f"ocena#{w.wskaznik_id}", doc_id="ocena", lokalizator=f"{kryterium} · {w.nazwa}",
                tekst=pseudo.tekst(" ".join(czesci), osoba_id),
            ))
    return wynik


def punkty_z_tresci(tresc: str | None) -> tuple[list[str], list[str]]:
    """Kwestie i argumenty z JSON-u w „tresc” (instrukcja core każe składać tresc z cytatów, stąd JSON jak w #164)."""
    try:
        dane = json.loads((tresc or "").strip())
    except ValueError:
        return [], []
    if not isinstance(dane, dict):
        return [], []

    def lista(klucz: str) -> list[str]:
        v = dane.get(klucz)
        return [str(x).strip() for x in v if str(x).strip()][:MAKS_PUNKTOW] if isinstance(v, list) else []

    return lista("kwestie"), lista("argumenty")


def _z_limitem(d):
    """Kopia dostawcy z dłuższym limitem czasu tylko dla przygotowania; asystent formalny zostaje przy swoim."""
    if getattr(d, "timeout", None) is None or d.timeout >= LIMIT_PRZYGOTOWANIA_S:
        return d
    kopia = copy.copy(d)
    kopia.timeout = LIMIT_PRZYGOTOWANIA_S
    return kopia


def przygotowanie(
    asystent: Asystent, pytanie: str, sciezka, oceny: list[Fragment]
) -> tuple[OdpowiedzAsystenta, list[str], list[str]] | None:
    """Odpowiedź modelu z kwestiami i argumentami; None = model zawiódł albo podsunął ocenę (wtedy dotychczasowy czat)."""
    dostawcy = [_z_limitem(d) for d in asystent.dostawcy if d.tryb != Tryb.EKSTRAKCYJNE]
    if not dostawcy or not oceny:
        return None
    # Jedna ponowna próba pierwszym modelem przed resztą łańcucha: odpowiedź odrzucona przez walidator
    # (np. liczba spoza cytatów, serwer 22.11: 1 z 3) zwykle przechodzi za drugim razem.
    dostawcy = [dostawcy[0], *dostawcy]
    fragmenty = [*oceny, *asystent.fragmenty_przepisow(pytanie, sciezka)]
    try:
        wynik = wywolaj(Zapytanie(
            operacja=OPERACJA_PRZYGOTOWANIA, prompt_wersja=asystent.konf.wersja,
            pytanie=f"{POLECENIE_PRZYGOTOWANIA}\n\nPYTANIE PRZEŁOŻONEGO: {pytanie}", fragmenty=fragmenty,
        ), dostawcy, asystent.dziennik)
    except BrakOdpowiedzi:
        return None
    kwestie, argumenty = punkty_z_tresci(wynik.odpowiedz.tresc)
    if not (kwestie or argumenty) or proponuje_ocene(" ".join([*kwestie, *argumenty])):
        return None
    po_id = {f.id: f for f in fragmenty}
    cytaty: list[CytatAsystenta] = []
    for c in wynik.odpowiedz.cytaty:
        f = po_id[c.fragment_id]
        if any(x.fragment_id == f.id for x in cytaty):
            continue
        cytaty.append(
            CytatAsystenta(
                fragment_id=f.id, doc_id=f.doc_id, dokument="Bieżąca ocena (dane z aplikacji)", lokalizator=f.lokalizator,
                strona=None, kategoria=Kategoria.FUNKCJA_APLIKACJI, cytat=f.tekst, wyrozniony=c.cytat,
            )
            if f.doc_id == "ocena"
            else asystent.cytat_fragmentu(f, pytanie)
        )
    odpowiedz = OdpowiedzAsystenta(
        pytanie=pytanie, sciezka=sciezka, znaleziono=True, cytaty=cytaty, tryb=wynik.tryb, dostawca=wynik.dostawca,
        odrzuceni=wynik.odrzuceni, pokrycie=1.0,
    )
    return odpowiedz, kwestie, argumenty


# Podpowiedź przy wskaźniku (Karol 22.11, 02:04: „to ma być podpowiedź taka inteligentna AI”). Model dostaje
# fragmenty modelu kompetencji dla wskaźnika (opis i 5 poziomów) oraz pseudonimizowane zadania z OSP i przykład;
# odpowiedź bez dosłownego cytatu z tych fragmentów odrzuca walidacja w core (wtedy zostaje pytanie z szablonu).
POLECENIE_PODPOWIEDZI = """Zaproponuj jedno krótkie pytanie (najwyżej dwa zdania), które przełożony zada
Ocenianemu w rozmowie oceniającej o tym wskaźniku. Pytanie ma przywołać konkretną sytuację z okresu oceny
przy zadaniach z opisu stanowiska i pomóc porównać zachowanie ze standardem (poziom „na poziomie oczekiwań”).
Zwracaj się do Ocenianego w drugiej osobie, bez imion. W polu "tresc" zwróć tekst z obiektem JSON
{"pytanie": "<pytanie zakończone znakiem zapytania>"}, a w "cytaty" dosłowny fragment opisu wskaźnika
albo poziomu, na którym je opierasz."""


def pytanie_z_tresci(tresc: str | None) -> tuple[str | None, str | None]:
    """Pytanie z pola ``tresc`` modelu i powód odrzucenia. Instrukcja core każe składać ``tresc`` z cytatów,
    więc polecenie prosi o JSON (jak cele_llm); tolerujemy też samo pytanie w cudzysłowie (#164)."""
    tekst = (tresc or "").strip()
    try:
        dane = json.loads(tekst)
        if isinstance(dane, dict):
            tekst = str(dane.get("pytanie") or "")
    except ValueError:
        pass
    tekst = tekst.strip().strip("„”\"'").strip()
    if not tekst:
        return None, "brak treści"
    if "?" not in tekst:
        return None, "nie jest pytaniem"
    if len(tekst) > 400:
        return None, "za długie"
    if proponuje_ocene(tekst):
        return None, "podsuwa ocenę"
    return tekst, None


class ZapytaniePodpowiedzi(BaseModel):
    wskaznik_id: str = Field(max_length=200)


class PodpowiedzRozmowy(BaseModel):
    pytanie: str | None
    """Pytanie z modelu; ``None``, gdy model nie odpowiedział poprawnie (ekran zostaje przy szablonie)."""
    dostawca: str | None = None
    tryb: str | None = None
    odrzucono: str | None = None
    """Dlaczego tekst modelu nie trafił na ekran (diagnostyka; bez treści odpowiedzi)."""


def router(
    auth: Autoryzacja,
    qnt: MockQnt,
    stan2: StanKroku2,
    konf: KonfiguracjaRozmowy,
) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["krok 6: asystent rozmowy"])

    @r.post("/procesy/{proces_id}/rozmowa")
    def plan_rozmowy(
        proces_id: int,
        request: Request,
        kontekst: KontekstRozmowy | None = None,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> PlanRozmowy:
        """Plan rozmowy oceniającej: zakres z przepisu, pytania z powiązaniem i uzasadnieniem,
        argumenty, szkic informacji zwrotnej i kwestie do omówienia. Wszystko jest sugestią
        do edycji; nic nie jest zapisywane i oceny się nie zmieniają. Tylko przełożony
        (``ocena.prowadz``): plan zawiera przykłady i uwagi o pracowniku."""
        baza = request.app.state.baza
        proces = wczytaj_proces(baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        p = qnt.pracownik(proces.osoba_id)
        if p is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", p.model_dump(), "ocena.prowadz")
        if proces.krok2 is None:
            raise HTTPException(409, "Najpierw zapisz kryteria i wskaźniki (krok 2).")
        oceny, decyzje = _wczytaj_dane(baza, proces.id)
        # Ta sama wersja metodyki co w krokach 3–5 (przypięta do procesu, #39).
        metodyki: RejestrMetodyk = request.app.state.metodyki
        konf_oceny = metodyki.konfiguracja(metodyki.dla_procesu(proces.id))
        stan = zbuduj_stan(
            proces.id, proces.sciezka, proces.arkusz, proces.krok2, oceny, decyzje, stan2.model, konf_oceny
        )
        return przygotuj(stan, proces.krok1.osp, kontekst or KontekstRozmowy(), konf, stan2.model)

    @r.post("/procesy/{proces_id}/rozmowa/czat")
    def czat_rozmowy(
        proces_id: int,
        body: PytanieCzatu,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> OdpowiedzCzatu:
        """RAG dla przełożonego z pseudonimizowanym kontekstem bieżącej oceny."""
        baza = request.app.state.baza
        proces = wczytaj_proces(baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        pracownik = qnt.pracownik(proces.osoba_id)
        if pracownik is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", pracownik.model_dump(), "ocena.prowadz")
        if proces.krok2 is None:
            raise HTTPException(409, "Najpierw zapisz kryteria i wskaźniki (krok 2).")

        oceny, decyzje = _wczytaj_dane(baza, proces.id)
        metodyki: RejestrMetodyk = request.app.state.metodyki
        konf_oceny = metodyki.konfiguracja(metodyki.dla_procesu(proces.id))
        stan = zbuduj_stan(
            proces.id,
            proces.sciezka,
            proces.arkusz,
            proces.krok2,
            oceny,
            decyzje,
            stan2.model,
            konf_oceny,
        )
        surowy_kontekst = {
            "osoba_id": proces.osoba_id,
            "przelozony_id": pracownik.przelozony_id,
            "sciezka": proces.sciezka,
            "wybrane_wskazniki_poziomy_i_decyzje": stan.model_dump(mode="json"),
        }
        pseudo = Pseudonimizator(qnt)
        przyg = przygotowanie(
            request.app.state.asystent, body.pytanie, proces.sciezka, fragmenty_oceny(stan, pseudo, proces.osoba_id)
        )
        if przyg is not None:
            odp, kwestie, argumenty = przyg
            return OdpowiedzCzatu(
                **odp.model_dump(), oznaczenie_sugestii=konf.oznaczenie_sugestii, kwestie=kwestie, argumenty=argumenty
            )
        kontekst = pseudo.json(surowy_kontekst, proces.osoba_id)
        odpowiedz = request.app.state.asystent.odpowiedz(
            body.pytanie, proces.sciezka, kontekst=kontekst
        )
        if odpowiedz.faq_id is None and proponuje_ocene(odpowiedz.tresc):
            odpowiedz = odpowiedz.model_copy(update={
                "tresc": None,
                "uwagi": [*odpowiedz.uwagi, "Asystent nie proponuje punktów ani poziomu; zostały same cytaty ze źródeł."],
            })
        return OdpowiedzCzatu(
            **odpowiedz.model_dump(), oznaczenie_sugestii=konf.oznaczenie_sugestii
        )

    @r.post("/procesy/{proces_id}/rozmowa/podpowiedz")
    def podpowiedz(
        proces_id: int,
        body: ZapytaniePodpowiedzi,
        request: Request,
        uz: Uzytkownik = auth.wymagaj("ocena.prowadz"),
    ) -> PodpowiedzRozmowy:
        """Pytanie do rozmowy przy wskaźniku z modelu (łańcuch dostawców asystenta, Scaleway w UE).
        Kontekst bez imion i nazwisk; podpowiedź, nie decyzja. 404 dla wskaźnika spoza kroku 2."""
        baza = request.app.state.baza
        proces = wczytaj_proces(baza, proces_id)
        if proces is None:
            raise HTTPException(404, "Nie ma takiego procesu")
        pracownik = qnt.pracownik(proces.osoba_id)
        if pracownik is None:
            raise HTTPException(404, "Nie ma takiej osoby w QNT")
        auth.sprawdz(uz, "pracownik", pracownik.model_dump(), "ocena.prowadz")
        if proces.krok2 is None:
            raise HTTPException(409, "Najpierw zapisz kryteria i wskaźniki (krok 2).")
        wybrane = {w.id for k in proces.krok2.kryteria for w in k.wskazniki}
        llm = request.app.state.cele_llm
        fragmenty = llm.fragmenty_wskaznikow.get(body.wskaznik_id) if body.wskaznik_id in wybrane else None
        if not fragmenty:
            raise HTTPException(404, "Ten wskaźnik nie należy do kryteriów tej oceny.")
        oceny, _ = _wczytaj_dane(baza, proces.id)
        o = oceny.get(body.wskaznik_id)
        osp = proces.krok1.osp
        kontekst = Pseudonimizator(qnt).json(
            {
                "zadania_osp": [z.tekst for z in (osp.zadania_dominujace if osp else [])],
                "przyklad": o.uwagi if o and o.uwagi else None,
            },
            proces.osoba_id,
        )
        zapytanie = Zapytanie(
            operacja="podpowiedz_rozmowy",
            prompt_wersja="1",
            pytanie=f"{POLECENIE_PODPOWIEDZI}\n\nKONTEKST (dane pseudonimizowane):\n{kontekst}",
            fragmenty=fragmenty,
        )
        if not llm.dostawcy:
            return PodpowiedzRozmowy(pytanie=None)
        try:
            wynik = wywolaj(zapytanie, llm.dostawcy, llm.dziennik)
        except BrakOdpowiedzi:
            return PodpowiedzRozmowy(pytanie=None)
        # Ma to być jedno pytanie do rozmowy, nie ocena ani wykład: inaczej zostaje pytanie z szablonu.
        pytanie, powod = pytanie_z_tresci(wynik.odpowiedz.tresc)
        return PodpowiedzRozmowy(pytanie=pytanie, dostawca=wynik.dostawca, tryb=str(wynik.tryb), odrzucono=powod)

    return r
