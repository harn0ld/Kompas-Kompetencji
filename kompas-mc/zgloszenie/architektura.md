# Technologie i architektura

## Technologie

| Warstwa | Technologia |
|---|---|
| Backend | Python 3.12, **FastAPI** (dokumentacja OpenAPI pod `/docs`), Pydantic, SQLite |
| Interfejs | **React + TypeScript + Vite**, przeglądarka na komputerze i tablecie (bez smartfonów, zgodnie z zadaniem) |
| Dokumenty | ReportLab (PDF z polskimi znakami), pypdf i openpyxl (ekstrakcja z PDF, DOCX i XLSX) |
| AI | BM25 na rdzeniach słów (własna implementacja, bez wektorów); łańcuch dostawców `LlmProvider` z `asystent.yaml`: DeepSeek v4 Flash przez Scaleway Generative APIs w UE (API zgodne z OpenAI, klucz `SCALEWAY_API_KEY`) → Ollama `qwen3:8b` → tryb ekstrakcyjny |
| Jakość | pytest (407 testów backendu MC, 101 testów core), 14 plików testów e2e (Playwright, jasny i ciemny motyw), walidator cytatów `kompas-waliduj` (231 cytatów, 0 błędów); wszystko uruchamiane ręcznie |

Wszystkie biblioteki są open source i nie wymagają płatnych usług.

## Architektura

```
┌──────────── Interfejs (React) ────────────┐
│ logowanie · lista podwładnych · kroki 1–8 │
│ czat asystenta · panel HR · panel źródeł  │
└───────────────────┬───────────────────────┘
                    │ REST/JSON (OpenAPI), token sesji
┌───────────────────▼───────────────────────┐
│ API wersji MC (FastAPI)                   │
│ procesy · kroki 1–8 · arkusze B/C i PDF   │
│ asystent formalny · asystent rozmowy · HR │
│ metodyka (wersje) · źródła i braki        │
├───────────────────────────────────────────┤
│ kompas-core (wspólny, bez treści)         │
│ korpus + walidator cytatów · BM25         │
│ kalendarz terminów · silnik skali § 11    │
│ uwierzytelnianie, role, dziennik zmian    │
│ LlmProvider z walidacją · prymitywy PDF   │
├───────────────────────────────────────────┤
│ Konfiguracja YAML (treść merytoryczna)    │
│ reguły z cytatami · model · FAQ · role    │
└───────────────────────────────────────────┘
      │                        │
  mock QNT (kadry)       mock EZD (rejestracja PDF)
```

- **Mechanizm oddzielony od treści.** `kompas-core` nie zna żadnych przepisów: dostaje je z konfiguracji. Zmiana progów, kryteriów, terminów czy treści oświadczeń to zmiana pliku YAML z cytatami, którą sprawdza walidator `kompas-waliduj`. Nie trzeba zmieniać kodu.
- **Wersjonowanie.** Metodyka sugestii ma wersje z zatwierdzeniem, a ocena zapisuje użytą wersję. Wynik można więc odtworzyć po zmianie reguł.
- **Integracje przez udokumentowane interfejsy.** Mock QNT (dane kadrowe) i mock EZD (rejestracja PDF z numerem sprawy i hashem) mają kontrakty w OpenAPI. Prawdziwe systemy podłącza się w miejsce mocków bez zmiany reszty.
- **Bezpieczeństwo w prototypie.** Logowanie kontami demo dostaje token sesji. Role i reguły dostępu egzekwuje API: przełożony widzi swoich podwładnych, oceniany siebie, a HR wszystkich, ale bez treści ocen i notatek. Dziennik zmian zapisuje: kto, kiedy, co, według której wersji reguł.
- **Dokumenty.** PDF arkusza B/C odwzorowuje wzór z rozporządzenia, ma wersję i hash w stopce i miejsca na podpis odręczny. Zatwierdzenie w aplikacji nie jest podpisem i aplikacja to komunikuje.

## Przed wdrożeniem produkcyjnym

| Obszar | Stan w prototypie | Co trzeba zrobić |
|---|---|---|
| Uwierzytelnianie | Konta demo z hasłem w konfiguracji, sesje w pamięci | SSO urzędu (np. Azure AD / Keycloak, OIDC), MFA, wygasanie i unieważnianie sesji |
| Autoryzacja | Role z pliku `role.yaml` | Role i podległość z systemu kadrowego, przegląd uprawnień, zasada najmniejszych uprawnień |
| Dane osobowe | Fikcyjne dane, SQLite bez szyfrowania | Baza z szyfrowaniem w spoczynku i w transmisji (TLS), retencja zgodna z przepisami o aktach osobowych, DPIA, rejestr czynności przetwarzania |
| Integracje | Mock QNT i mock EZD | Prawdziwe API QNT i EZD, uwierzytelnienie usług (mTLS / klucze), obsługa błędów i kolejki |
| AI | Łańcuch z `asystent.yaml`: DeepSeek v4 Flash przez Scaleway (UE) → Ollama → ekstrakcyjny; bez klucza i Ollamy odpowiada tryb ekstrakcyjny | Model hostowany w infrastrukturze MC (dane nie opuszczają urzędu), testy jakości na pytaniach od ekspertów HR, monitorowanie odpowiedzi i logów |
| Baza wiedzy | Materiały MC i ustawa o służbie cywilnej (tekst jednolity Dz.U. 2026 poz. 590 z ISAP, stan prawny na 14.04.2026) | Aktualizacja ustawy po zmianach (najbliższa: Dz.U. 2026 poz. 26 od 1.01.2027), aktualne poradniki KPRM, proces aktualizacji przepisów z zatwierdzaniem |
| Metodyka | Mediana i mapowanie 5→3 jako decyzja projektowa | Zatwierdzenie przez właściciela metodyki w MC (w aplikacji: wersja z osobą i datą) |
| Podpis | PDF do podpisu odręcznego | Ewentualny podpis kwalifikowany lub podpis w EZD, zgodnie z decyzją prawną |
| Dziennik i audyt | Tabela w SQLite | Niezmienialny dziennik audytowy, kopie zapasowe, monitorowanie |
| Dostępność | Interfejs bez audytu WCAG | Audyt WCAG 2.1 AA, testy z użytkownikami |
| Wydajność | Korpus budowany przy starcie | Cache korpusu, wiele instancji API, baza serwerowa (PostgreSQL) |

## Plan rozwoju bazy wiedzy

Dziś dokument dodaje się plikiem w `materialy mc/`, wpisem w `konfiguracja/korpus.yaml` i restartem API (checklista w `kompas-mc/README.md`). Korpus i indeks powstają w pamięci przy starcie. Wersję (`doc_version`) ma 4 z 13 dokumentów. Kolejne kroki, w tej kolejności:

1. **Wersje dokumentów z zatwierdzaniem**, na wzór metodyki sugestii (`metodyka.py`): nowa wersja ma stan PROJEKT, przechodzi walidację cytatów i pomiar zestawów pytań, a po zatwierdzeniu przez wskazaną osobę dostaje stan ZATWIERDZONA.
2. **Data obowiązywania** przy każdej wersji aktu w manifeście.
3. **Przypięcie wersji korpusu do procesu oceny**, jak dziś wersji metodyki: ocena zapamiętuje, z jakiej bazy wiedzy korzystała.
4. **Dziennik zmian korpusu**: kto, kiedy i jaki plik dodał lub podmienił.
5. **Stabilne identyfikatory fragmentów** (dziś numer kolejny w pliku: po podmianie pliku bez `doc_version` ten sam identyfikator wskazuje inną treść).
6. **Przeładowanie bez restartu z walidacją**: nowy korpus zastępuje działający dopiero wtedy, gdy walidator cytatów i cytaty FAQ nie zgłoszą błędu; inaczej aktywacja jest odrzucana.

## Kod i uruchomienie

Instrukcja jest w `kompas-mc/README.md`: API na porcie 8002, interfejs na 5174, testy i walidator jedną komendą.
