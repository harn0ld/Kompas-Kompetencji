"""Interfejs ``LlmProvider``, dostawcy i bezpieczne wywołanie z fallbackiem."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from ..zrodla.korpus import Korpus
from ..zrodla.model import StatusEkstrakcji, WynikEkstrakcji
from ..zrodla.walidator import cytat_w_tekscie
from .model import Odpowiedz, Tryb, WpisLogu, WynikLlm, Zapytanie

_log = logging.getLogger(__name__)


@runtime_checkable
class LlmProvider(Protocol):
    """Dostawca odpowiedzi. Może zgłosić wyjątek (brak sieci, klucza, limitu):
    ``wywolaj()`` potraktuje to jak odrzucenie i przejdzie do następnego."""

    nazwa: str
    model: str | None
    tryb: Tryb

    def odpowiedz(self, zapytanie: Zapytanie) -> Odpowiedz: ...


class Dziennik(Protocol):
    def zapisz(self, wpis: WpisLogu) -> None: ...


class DziennikPamiec:
    """Log w pamięci (testy, demo)."""

    def __init__(self) -> None:
        self.wpisy: list[WpisLogu] = []

    def zapisz(self, wpis: WpisLogu) -> None:
        self.wpisy.append(wpis)


class DziennikJsonl:
    """Log dopisywany do pliku JSON Lines."""

    def __init__(self, plik: str | Path) -> None:
        self.plik = Path(plik)

    def zapisz(self, wpis: WpisLogu) -> None:
        self.plik.parent.mkdir(parents=True, exist_ok=True)
        with self.plik.open("a", encoding="utf-8") as f:
            f.write(wpis.model_dump_json() + "\n")


# --- dostawcy -----------------------------------------------------------------------


class Ekstrakcyjny:
    """Bez LLM, bez sieci i klucza. Zwraca najlepsze fragmenty (BM25 wobec pytania)
    jako cytaty; ``tresc`` to złączone cytaty. Gdy nic nie pasuje, zwraca pustą
    listę cytatów, czyli odpowiedź, którą ``wywolaj()`` odrzuci („brak informacji”)."""

    nazwa = "ekstrakcyjny"
    model = None
    tryb = Tryb.EKSTRAKCYJNE

    def __init__(self, k: int = 3) -> None:
        self.k = k

    def odpowiedz(self, zapytanie: Zapytanie) -> Odpowiedz:
        korpus = Korpus(
            [
                WynikEkstrakcji(
                    doc_id="zapytanie", plik="", status=StatusEkstrakcji.OK,
                    fragmenty=zapytanie.fragmenty,
                )
            ]
        )
        trafienia = korpus.wyszukaj(zapytanie.pytanie, k=self.k)
        cytaty = [{"fragment_id": t.fragment_id, "cytat": t.fragment.tekst} for t in trafienia]
        tresc = "\n\n".join(t.fragment.tekst for t in trafienia) or None
        return Odpowiedz.model_validate({"cytaty": cytaty, "tresc": tresc})


class Zapisane:
    """Odpowiedzi zapisane wcześniej dla scenariuszy demo (plik JSON).

    Klucz to ``klucz_zapytania(zapytanie)``. Brak zapisu ⇒ ``KeyError``.
    """

    nazwa = "zapisane"
    model = None
    tryb = Tryb.ZAPISANE

    def __init__(self, plik: str | Path) -> None:
        self.plik = Path(plik)
        self._dane: dict[str, Any] = (
            json.loads(self.plik.read_text(encoding="utf-8")) if self.plik.exists() else {}
        )

    def odpowiedz(self, zapytanie: Zapytanie) -> Odpowiedz:
        klucz = klucz_zapytania(zapytanie)
        if klucz not in self._dane:
            raise KeyError(f"brak zapisanej odpowiedzi dla {klucz[:12]}…")
        return Odpowiedz.model_validate(self._dane[klucz])

    @staticmethod
    def dopisz(plik: str | Path, zapytanie: Zapytanie, odpowiedz: Odpowiedz) -> None:
        """Zapisuje odpowiedź (np. z wywołania na żywo) do pliku scenariuszy demo."""
        plik = Path(plik)
        dane = json.loads(plik.read_text(encoding="utf-8")) if plik.exists() else {}
        dane[klucz_zapytania(zapytanie)] = odpowiedz.model_dump()
        plik.write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding="utf-8")


_INSTRUKCJA = """Odpowiadasz wyłącznie na podstawie podanych fragmentów źródeł. Fragmenty to dokumenty (przepisy, poradniki, opracowania, instrukcje aplikacji) oraz dane o pracowniku (wszystko, co aplikacja wie o osobie: stanowisko, zadania, notatki, przykłady, oceny). Każde twierdzenie opierasz na fragmencie i zawsze się do niego odnosisz cytatem.
Zwróć tylko obiekt JSON:
{"cytaty": [{"fragment_id": "<ID fragmentu>", "cytat": "<dosłowny fragment tekstu>"}],
 "wybor": ["<ID z katalogu>"], "tresc": "<krótkie podsumowanie albo null>"}
Zasady: cytat kopiuj znak po znaku z fragmentu o podanym ID. Nie używaj wiedzy spoza fragmentów. Gdy wiadomość ma wiersz „Podsumowanie: tak”, wpisz w "tresc" krótkie podsumowanie (1–3 zdania) na podstawie cytowanych fragmentów; liczby, daty i terminy przepisuj wyłącznie z cytatów. Gdy ma „Podsumowanie: nie”, "tresc" = null. Gdy ma „Podsumowanie: format z pytania”, wypełnij "tresc" tak, jak opisuje pytanie. "wybor" zawiera tylko ID z katalogu. Jeśli fragmenty nie odpowiadają na pytanie, zwróć {"cytaty": [], "wybor": [], "tresc": null}."""


# Asystent formalny dostaje własne krótkie podsumowanie modelu (Karol 22.11). Pozostałe operacje
# opisują format pola "tresc" w pytaniu (JSON z kwestiami, celami, zdaniami opisu).
_PODSUMOWANIE = {"asystent_formalny": "tak"}


def _system(z: Zapytanie) -> str:
    """Prompt główny aplikacji (jeśli jest) przed wspólną instrukcją techniczną."""
    return f"{z.rola}\n\n{_INSTRUKCJA}" if z.rola else _INSTRUKCJA


def _wiadomosc(z: Zapytanie) -> str:
    fragmenty = "\n\n".join(f"[{f.id}]\n{f.tekst}" for f in z.fragmenty)
    katalog = ", ".join(z.katalog) if z.katalog else "(brak — nie wybieraj)"
    podsumowanie = _PODSUMOWANIE.get(z.operacja, "format z pytania")
    return (f"Operacja: {z.operacja}\nKatalog: {katalog}\nPodsumowanie: {podsumowanie}\n\n"
            f"FRAGMENTY:\n{fragmenty}\n\nPYTANIE: {z.pytanie}")


def _parsuj(tekst: str) -> Odpowiedz:
    m = re.search(r"\{.*\}", tekst, re.DOTALL)
    if not m:
        raise ValueError("odpowiedź modelu nie zawiera JSON")
    dane = json.loads(m.group(0))
    return Odpowiedz.model_validate(
        {
            "cytaty": dane.get("cytaty") or [],
            "wybor": dane.get("wybor") or [],
            "tresc": dane.get("tresc"),
        }
    )


def _post_json(url: str, dane: dict, naglowki: dict[str, str], timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(dane).encode("utf-8"),
        headers={"content-type": "application/json", **naglowki},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - URL z konfiguracji
        return json.loads(r.read().decode("utf-8"))


class Anthropic:
    """Anthropic Messages API (``ANTHROPIC_API_KEY``). Model zwraca JSON
    ``{"cytaty": [...], "wybor": [...], "tresc": ...}``."""

    nazwa = "anthropic"
    tryb = Tryb.NA_ZYWO
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str, api_key: str | None = None, timeout: float = 30) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def odpowiedz(self, zapytanie: Zapytanie) -> Odpowiedz:
        klucz = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not klucz:
            raise RuntimeError("brak ANTHROPIC_API_KEY")
        wynik = _post_json(
            self.URL,
            {
                "model": self.model,
                "max_tokens": 2048,
                "system": _system(zapytanie),
                "messages": [{"role": "user", "content": _wiadomosc(zapytanie)}],
            },
            {"x-api-key": klucz, "anthropic-version": "2023-06-01"},
            self.timeout,
        )
        tekst = "".join(b.get("text", "") for b in wynik.get("content", []) if b.get("type") == "text")
        return _parsuj(tekst)


class OpenAiZgodny:
    """Dostawca zgodny z OpenAI Chat Completions API.

    Klucz jest odczytywany dopiero przy wywołaniu z nazwy zmiennej środowiskowej
    podanej w konfiguracji. Dzięki temu konfiguracja nie zawiera sekretów, a brak
    klucza uruchamia zwykły fallback w :func:`wywolaj`.
    """

    nazwa = "openai_zgodny"
    tryb = Tryb.NA_ZYWO

    def __init__(
        self,
        base_url: str,
        model: str,
        zmienna_klucza: str,
        timeout: float = 30,
        temperatura: float | None = None,
        zmienna_adresu: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.zmienna_klucza = zmienna_klucza
        self.zmienna_adresu = zmienna_adresu
        """Opcjonalna zmienna środowiskowa z adresem API (np. Scaleway z identyfikatorem projektu dla klucza
        o uprawnieniach tylko do jednego projektu); pusta albo brak = ``base_url`` z konfiguracji."""
        self.timeout = timeout
        self.temperatura = temperatura

    def _adres(self) -> str:
        nadpisany = os.environ.get(self.zmienna_adresu) if self.zmienna_adresu else None
        return (nadpisany or self.base_url).rstrip("/")

    def odpowiedz(self, zapytanie: Zapytanie) -> Odpowiedz:
        klucz = os.environ.get(self.zmienna_klucza)
        if not klucz:
            raise RuntimeError(f"brak {self.zmienna_klucza}")
        dane: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _system(zapytanie)},
                {"role": "user", "content": _wiadomosc(zapytanie)},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.temperatura is not None:
            dane["temperature"] = self.temperatura
        wynik = _post_json(
            f"{self._adres()}/chat/completions",
            dane,
            {"authorization": f"Bearer {klucz}"},
            self.timeout,
        )
        return _parsuj(wynik["choices"][0]["message"]["content"])


class Ollama:
    """Lokalny model przez API Ollama (``/api/chat``), bez klucza."""

    nazwa = "ollama"
    tryb = Tryb.NA_ZYWO

    def __init__(
        self, model: str, url: str = "http://localhost:11434", timeout: float = 60
    ) -> None:
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout

    def odpowiedz(self, zapytanie: Zapytanie) -> Odpowiedz:
        wynik = _post_json(
            f"{self.url}/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": _system(zapytanie)},
                    {"role": "user", "content": _wiadomosc(zapytanie)},
                ],
            },
            {},
            self.timeout,
        )
        return _parsuj(wynik["message"]["content"])


# --- wywołanie ------------------------------------------------------------------------


def klucz_zapytania(zapytanie: Zapytanie) -> str:
    """Stabilny skrót (sha256) operacji, wersji promptu, pytania i ID fragmentów."""
    dane = [
        zapytanie.operacja,
        zapytanie.prompt_wersja,
        zapytanie.pytanie,
        [f.id for f in zapytanie.fragmenty],
        sorted(zapytanie.katalog),
    ]
    return hashlib.sha256(json.dumps(dane, ensure_ascii=False).encode("utf-8")).hexdigest()


def sprawdz_odpowiedz(zapytanie: Zapytanie, odpowiedz: Odpowiedz) -> list[str]:
    """Błędy walidacji (pusta lista = poprawna):

    - co najmniej jeden cytat;
    - każdy ``fragment_id`` pochodzi z ``zapytanie.fragmenty``;
    - każdy cytat występuje w tym fragmencie (normalizacja walidatora CORE-1);
    - każdy ``wybor`` pochodzi z ``zapytanie.katalog``.
    """
    bledy: list[str] = []
    fragmenty = {f.id: f for f in zapytanie.fragmenty}
    if not odpowiedz.cytaty:
        bledy.append("brak cytatów: brak wystarczających informacji we fragmentach")
    for c in odpowiedz.cytaty:
        f = fragmenty.get(c.fragment_id)
        if f is None:
            bledy.append(f"fragment {c.fragment_id} nie był w zapytaniu")
        elif not cytat_w_tekscie(c.cytat, f.tekst):
            bledy.append(f"cytat bez pokrycia we fragmencie {c.fragment_id}: „{c.cytat[:80]}”")
    katalog = set(zapytanie.katalog)
    for w in odpowiedz.wybor:
        if w not in katalog:
            bledy.append(f"wybór {w} spoza katalogu")
    if odpowiedz.tresc and zapytanie.operacja.startswith("asystent"):
        # Helix G3 (3), tylko asystent formalny (opis osoby i cele liczą liczby z faktów, nie z korpusu): treść ma być ułożona z cytowanych fragmentów. Liczba (dni, paragraf, punkty, data) spoza
        # cytowanych fragmentów i pytania to twierdzenie bez źródła → walidacja odrzuca, łańcuch idzie dalej.
        # ponytail: tylko liczby; zmyślenie słowne („siedem”) wymaga sprawdzenia semantycznego.
        # Tylko cytowane fragmenty (tekst i lokalizator, np. „art. 83”); liczba z pytania niczego nie dowodzi
        # (runda 2: „czy termin wynosi 99 dni?” przepuszczało „99 dni” w odpowiedzi).
        cytowane = [fragmenty[c.fragment_id] for c in odpowiedz.cytaty if c.fragment_id in fragmenty]
        dozwolone = set(_liczby(" ".join(f"{f.lokalizator} {f.tekst}" for f in cytowane)))
        obce = [n for n in _liczby(_BEZ_NUMEROW_LISTY.sub("", odpowiedz.tresc)) if n not in dozwolone]
        if obce:
            bledy.append(f"liczby w treści bez pokrycia w cytowanych fragmentach: {', '.join(dict.fromkeys(obce))}")
    return bledy


_LICZBA = re.compile(r"\d+(?:[.,]\d+)?")
_BEZ_NUMEROW_LISTY = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)


def _liczby(tekst: str) -> list[str]:
    return [n.replace(",", ".") for n in _LICZBA.findall(tekst)]


class BrakOdpowiedzi(RuntimeError):
    """Żaden dostawca nie dał poprawnej odpowiedzi. ``wpisy`` to próby z logu."""

    def __init__(self, wpisy: list[WpisLogu]) -> None:
        super().__init__("brak poprawnej odpowiedzi: " + "; ".join(
            f"{w.dostawca}: {', '.join(w.bledy)}" for w in wpisy
        ))
        self.wpisy = wpisy


def wywolaj(
    zapytanie: Zapytanie,
    dostawcy: Sequence[LlmProvider],
    dziennik: Dziennik,
    zegar: Callable[[], datetime] = datetime.now,
) -> WynikLlm:
    """Pyta dostawców po kolei; pierwsza poprawna odpowiedź wygrywa. Każda próba
    trafia do dziennika; błąd zapisu dziennika idzie do ``logging`` i nie przerywa
    odpowiedzi. Gdy nikt nie odpowie poprawnie: ``BrakOdpowiedzi``.
    Na końcu listy warto mieć ``Ekstrakcyjny``, który działa zawsze."""
    proby: list[WpisLogu] = []
    for d in dostawcy:
        odpowiedz: Odpowiedz | None = None
        try:
            odpowiedz = d.odpowiedz(zapytanie)
            bledy = sprawdz_odpowiedz(zapytanie, odpowiedz)
        except (Exception) as e:  # noqa: BLE001 - każdy błąd dostawcy oznacza fallback
            if isinstance(e, ValidationError):
                bledy = [f"niepoprawny format odpowiedzi: {e.error_count()} błędów"]
            else:
                bledy = [f"{type(e).__name__}: {e}"]
        wpis = WpisLogu(
            czas=zegar(),
            operacja=zapytanie.operacja,
            dostawca=d.nazwa,
            model=d.model,
            prompt_wersja=zapytanie.prompt_wersja,
            fragment_ids=[f.id for f in zapytanie.fragmenty],
            tryb=d.tryb,
            walidacja_ok=not bledy,
            bledy=bledy,
            odpowiedz=odpowiedz,
        )
        try:
            dziennik.zapisz(wpis)
        except Exception:  # noqa: BLE001 - dziennik nie może przerwać odpowiedzi
            _log.exception("nie zapisano wpisu dziennika LLM (%s)", d.nazwa)
        proby.append(wpis)
        if not bledy:
            return WynikLlm(
                odpowiedz=odpowiedz,
                dostawca=d.nazwa,
                model=d.model,
                tryb=d.tryb,
                odrzuceni=[p.dostawca for p in proby[:-1]],
            )
    raise BrakOdpowiedzi(proby)


_TYPY: dict[str, Callable[[dict[str, Any]], LlmProvider]] = {
    "anthropic": lambda c: Anthropic(model=c["model"], timeout=c.get("timeout", 30)),
    "openai_zgodny": lambda c: OpenAiZgodny(
        base_url=c["base_url"],
        model=c["model"],
        zmienna_klucza=c["zmienna_klucza"],
        zmienna_adresu=c.get("zmienna_adresu"),
        timeout=c.get("timeout", 30),
        temperatura=c.get("temperatura"),
    ),
    "ollama": lambda c: Ollama(
        model=c["model"], url=c.get("url", "http://localhost:11434"), timeout=c.get("timeout", 60)
    ),
    "zapisane": lambda c: Zapisane(c["plik"]),
    "ekstrakcyjny": lambda c: Ekstrakcyjny(k=c.get("k", 3)),
}


def z_konfiguracji(konfiguracja: dict[str, Any]) -> list[LlmProvider]:
    """Łańcuch dostawców z konfiguracji wersji, np.::

        dostawcy:
          - {typ: ollama, model: llama3.1}
          - {typ: zapisane, plik: demo/llm.json}
          - {typ: ekstrakcyjny}

    ``dozwolone`` (opcjonalnie) ogranicza typy, np. ``[ollama, zapisane,
    ekstrakcyjny]``; typ spoza listy ⇒ ``ValueError``.
    """
    dozwolone = konfiguracja.get("dozwolone")
    wynik: list[LlmProvider] = []
    for i, c in enumerate(konfiguracja.get("dostawcy") or []):
        typ = c.get("typ")
        if typ not in _TYPY:
            raise ValueError(f"dostawcy[{i}]: nieznany typ {typ!r} (znane: {sorted(_TYPY)})")
        if dozwolone is not None and typ not in dozwolone:
            raise ValueError(f"dostawcy[{i}]: typ {typ!r} niedozwolony w tej wersji")
        wynik.append(_TYPY[typ](c))
    if not wynik:
        raise ValueError("konfiguracja nie ma żadnego dostawcy")
    return wynik
