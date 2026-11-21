"""Ustawienia aplikacji. Każde można nadpisać zmienną środowiskową."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

KATALOG_MC = Path(__file__).resolve().parents[3]  # kompas-mc/
PORT_DOMYSLNY = 8002


def wczytaj_env(plik: str | Path) -> None:
    """Wczytaj prosty plik ``KEY=VALUE`` bez nadpisywania środowiska procesu."""
    sciezka = Path(plik)
    if not sciezka.exists():
        return
    for nr, surowa in enumerate(sciezka.read_text(encoding="utf-8").splitlines(), start=1):
        linia = surowa.strip()
        if not linia or linia.startswith("#"):
            continue
        if linia.startswith("export "):
            linia = linia.removeprefix("export ").lstrip()
        if "=" not in linia:
            raise ValueError(f"{sciezka}:{nr}: oczekiwano NAZWA=WARTOSC")
        nazwa, wartosc = linia.split("=", 1)
        nazwa = nazwa.strip()
        if not nazwa or not nazwa.replace("_", "a").isalnum():
            raise ValueError(f"{sciezka}:{nr}: niepoprawna nazwa zmiennej")
        wartosc = wartosc.strip()
        if len(wartosc) >= 2 and wartosc[0] == wartosc[-1] and wartosc[0] in "\"'":
            wartosc = wartosc[1:-1]
        os.environ.setdefault(nazwa, wartosc)


@dataclass(frozen=True)
class Ustawienia:
    port: int
    manifest: Path
    konfiguracja_asystenta: Path
    braki: Path
    rozwoj: Path
    baza: Path
    log_llm: Path
    role: Path
    qnt: Path
    krok1: Path
    krok2: Path
    ocena: Path
    rozmowa: Path
    wynik_okresowy: Path = KATALOG_MC / "konfiguracja" / "wynik-okresowy.yaml"
    terminy_okresowej: Path = KATALOG_MC / "konfiguracja" / "terminy-okresowej.yaml"
    wzory_arkuszy: Path = KATALOG_MC / "konfiguracja" / "wzory-arkuszy.json"
    wynik_pierwszej: Path = KATALOG_MC / "konfiguracja" / "wynik-pierwszej.yaml"
    terminy_pierwszej: Path = KATALOG_MC / "konfiguracja" / "terminy-pierwszej.yaml"
    samoocena: Path = KATALOG_MC / "konfiguracja" / "samoocena.yaml"
    cele: Path = KATALOG_MC / "konfiguracja" / "cele.yaml"

    @classmethod
    def ze_srodowiska(cls) -> Ustawienia:
        wczytaj_env(KATALOG_MC / "backend" / ".env")
        konf = KATALOG_MC / "konfiguracja"
        dane = Path(os.environ.get("KOMPAS_MC_DANE", KATALOG_MC / "backend" / "dane"))
        return cls(
            port=int(os.environ.get("KOMPAS_MC_PORT", PORT_DOMYSLNY)),
            manifest=Path(os.environ.get("KOMPAS_MC_MANIFEST", konf / "korpus.yaml")),
            konfiguracja_asystenta=Path(
                os.environ.get("KOMPAS_MC_ASYSTENT", konf / "asystent.yaml")
            ),
            braki=Path(os.environ.get("KOMPAS_MC_BRAKI", konf / "braki.yaml")),
            rozwoj=Path(os.environ.get("KOMPAS_MC_ROZWOJ", konf / "rozwoj.yaml")),
            baza=Path(os.environ.get("KOMPAS_MC_BAZA", dane / "kompas-mc.db")),
            log_llm=dane / "llm.jsonl",
            role=Path(os.environ.get("KOMPAS_MC_ROLE", konf / "role.yaml")),
            qnt=Path(os.environ.get("KOMPAS_MC_QNT", konf / "qnt.yaml")),
            krok1=Path(os.environ.get("KOMPAS_MC_KROK1", konf / "krok1.yaml")),
            krok2=Path(os.environ.get("KOMPAS_MC_KROK2", konf / "krok2.yaml")),
            ocena=Path(os.environ.get("KOMPAS_MC_OCENA", konf / "ocena.yaml")),
            rozmowa=Path(os.environ.get("KOMPAS_MC_ROZMOWA", konf / "rozmowa.yaml")),
            wynik_okresowy=Path(os.environ.get("KOMPAS_MC_WYNIK_OKRESOWY", konf / "wynik-okresowy.yaml")),
            terminy_okresowej=Path(os.environ.get("KOMPAS_MC_TERMINY_OKRESOWEJ", konf / "terminy-okresowej.yaml")),
            wzory_arkuszy=Path(os.environ.get("KOMPAS_MC_WZORY_ARKUSZY", konf / "wzory-arkuszy.json")),
            wynik_pierwszej=Path(os.environ.get("KOMPAS_MC_WYNIK_PIERWSZEJ", konf / "wynik-pierwszej.yaml")),
            terminy_pierwszej=Path(os.environ.get("KOMPAS_MC_TERMINY_PIERWSZEJ", konf / "terminy-pierwszej.yaml")),
            samoocena=Path(os.environ.get("KOMPAS_MC_SAMOOCENA", konf / "samoocena.yaml")),
            cele=Path(os.environ.get("KOMPAS_MC_CELE", konf / "cele.yaml")),
        )
