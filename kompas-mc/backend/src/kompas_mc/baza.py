"""Baza SQLite aplikacji Kompas Kompetencji."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

WERSJA_SCHEMATU = "9"


CZAS_OCZEKIWANIA_S = 30
"""Ile wątek czeka na zwolnienie blokady zapisu (inny wątek w transakcji)."""


class Baza:
    """Połączenie z bazą bezpieczne dla wielu wątków (#82).

    Endpointy FastAPI są synchroniczne i działają w puli wątków, a jedno współdzielone
    połączenie `sqlite3` dawało przy równoczesnych zapytaniach fałszywe 404/409/500. Każdy
    wątek dostaje więc własne połączenie (tryb WAL: czytanie nie blokuje się z zapisem).
    Obiekt zachowuje interfejs `sqlite3.Connection` (`execute`, `with baza:`, `commit`,
    `close`), więc kod endpointów się nie zmienia. Cała obsługa jednego zapytania działa
    w jednym wątku, dlatego transakcja `with baza:` i `rowcount`/`lastrowid` dotyczą
    zawsze tego samego połączenia.
    """

    def __init__(self, plik: Path) -> None:
        self.plik = plik
        self._lokalne = threading.local()
        self._wszystkie: list[sqlite3.Connection] = []
        self._blokada = threading.Lock()

    def polaczenie(self) -> sqlite3.Connection:
        conn = getattr(self._lokalne, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.plik, timeout=CZAS_OCZEKIWANIA_S, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(f"PRAGMA busy_timeout={CZAS_OCZEKIWANIA_S * 1000}")
            self._lokalne.conn = conn
            with self._blokada:
                self._wszystkie.append(conn)
        return conn

    def execute(self, *args, **kwargs) -> sqlite3.Cursor:
        return self.polaczenie().execute(*args, **kwargs)

    def commit(self) -> None:
        self.polaczenie().commit()

    def __enter__(self) -> sqlite3.Connection:
        return self.polaczenie().__enter__()

    def __exit__(self, *exc) -> bool | None:
        return self.polaczenie().__exit__(*exc)

    def close(self) -> None:
        with self._blokada:
            for conn in self._wszystkie:
                conn.close()
            self._wszystkie.clear()
        self._lokalne = threading.local()


def polacz(plik: str | Path) -> Baza:
    plik = Path(plik)
    plik.parent.mkdir(parents=True, exist_ok=True)
    baza = Baza(plik)
    conn = baza.polaczenie()
    conn.execute("CREATE TABLE IF NOT EXISTS meta (klucz TEXT PRIMARY KEY, wartosc TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notatki (id INTEGER PRIMARY KEY, osoba_id TEXT NOT NULL,"
        " autor TEXT NOT NULL, tresc TEXT NOT NULL, czas TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS procesy (id INTEGER PRIMARY KEY, osoba_id TEXT NOT NULL,"
        " sciezka TEXT NOT NULL, arkusz TEXT NOT NULL, krok INTEGER NOT NULL, status TEXT NOT NULL,"
        " rozpoczal TEXT NOT NULL, rozpoczeto TEXT NOT NULL, zgodna_z_propozycja INTEGER NOT NULL,"
        " uzasadnienie TEXT, krok1 TEXT NOT NULL, krok2 TEXT)"
    )
    kolumny = {w[1] for w in conn.execute("PRAGMA table_info(procesy)")}
    # Kolejne kroki mogą otworzyć bazę utworzoną przez starszą wersję.
    for nazwa in ("krok2", "oceny_wskaznikow", "decyzje", "wynik_okresowy", "arkusz_okresowy", "pierwsza_ocena"):
        if nazwa not in kolumny:
            conn.execute(f"ALTER TABLE procesy ADD COLUMN {nazwa} TEXT")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rejestr_ezd (id INTEGER PRIMARY KEY, proces_id INTEGER NOT NULL,"
        " odcisk TEXT NOT NULL, zarejestrowano TEXT NOT NULL, sha256_pdf TEXT NOT NULL,"
        " pdf BLOB NOT NULL, UNIQUE (proces_id, odcisk))"
    )
    # Samoocena pracownika (#8): nagłówek procesu i pozycje przy wskaźnikach wybranych w kroku 2.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS samoocena (proces_id INTEGER PRIMARY KEY, status TEXT NOT NULL,"
        " zmieniono TEXT NOT NULL, przekazano TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS samoocena_pozycje (proces_id INTEGER NOT NULL, wskaznik_id TEXT NOT NULL,"
        " poziom INTEGER, brak_zdania INTEGER NOT NULL, przyklad TEXT, PRIMARY KEY (proces_id, wskaznik_id))"
    )
    # Cele rozwojowe pracownika (#10): należą do osoby, nie do procesu oceny.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cele (id INTEGER PRIMARY KEY, osoba_id TEXT NOT NULL, nazwa TEXT NOT NULL,"
        " opis TEXT, wskaznik_id TEXT, miernik TEXT, termin TEXT, status TEXT NOT NULL, komentarz TEXT,"
        " zgloszono_osiagniecie TEXT, autor TEXT NOT NULL, utworzono TEXT NOT NULL, zmieniono TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO meta (klucz, wartosc) VALUES ('wersja_aplikacji', 'mc-bdg')"
    )
    conn.execute(
        "INSERT INTO meta (klucz, wartosc) VALUES ('wersja_schematu', ?)"
        " ON CONFLICT(klucz) DO UPDATE SET wartosc = excluded.wartosc"
        " WHERE CAST(meta.wartosc AS INTEGER) < CAST(excluded.wartosc AS INTEGER)",
        (WERSJA_SCHEMATU,),
    )
    conn.commit()
    return baza
