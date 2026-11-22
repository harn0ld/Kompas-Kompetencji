# Kompas Kompetencji

Aplikacja korzysta z mechanizmów w `kompas-core/`. Jej źródłami są wyłącznie
pliki z folderu `materialy mc/`, którego zawartość jest tylko do odczytu.

| Część | Katalog | Port | Dane |
|---|---|---|---|
| API (FastAPI) | `backend/` | **8002** (`KOMPAS_MC_PORT`) | `backend/dane/kompas-mc.db`, log LLM `backend/dane/llm.jsonl` |
| Interfejs (React + Vite) | `frontend/` | **5174** | proxy `/api` → 8002 (`KOMPAS_MC_API`) |
| Konfiguracja | `konfiguracja/` | — | `korpus.yaml` (manifest źródeł), `asystent.yaml`, `role.yaml` (konta demo i uprawnienia), `qnt.yaml` (fikcyjni pracownicy) |

## Uruchomienie

Wymagane: Python ≥ 3.11 z [uv](https://docs.astral.sh/uv/) oraz Node ≥ 20.

```sh
# terminal 1: API na http://127.0.0.1:8002 (docs: /docs)
cd kompas-mc/backend && uv sync && uv run kompas-mc

# terminal 2: interfejs na http://127.0.0.1:5174
cd kompas-mc/frontend && npm ci && npm run dev
```

Start API trwa kilka sekund, bo przy starcie powstaje korpus z plików MC.

## Asystent formalny

`POST /api/asystent {"pytanie": "...", "sciezka": "pierwsza" | "okresowa" | null}`

- Domyślny łańcuch to DeepSeek v4 Flash hostowany w Scaleway Generative APIs
  (`deepseek-v4-flash-0731`, serwery w UE, Paryż) → lokalna Ollama (`qwen3:8b`)
  → tryb ekstrakcyjny BM25. Zapytania nie trafiają bezpośrednio do dostawcy modelu.
  Brak klucza, sieci lub Ollamy nie przerywa odpowiedzi: asystent przechodzi do
  następnego dostawcy.
- Aby włączyć model, skopiuj `backend/.env.example` jako `backend/.env` i ustaw
  `SCALEWAY_API_KEY` (klucz IAM z uprawnieniem GenerativeApisModelAccess). Klucz ograniczony do
  jednego projektu wymaga też `SCALEWAY_BASE_URL=https://api.scaleway.ai/<id projektu>/v1`. Plik
  `.env` jest ignorowany przez Git. Aby wyłączyć model, usuń wartość klucza;
  kolejność dostawców zmienia się w `konfiguracja/asystent.yaml`.
- Listę modeli można sprawdzić bez ujawniania klucza poleceniem
  `curl -sS https://api.scaleway.ai/v1/models -H "Authorization: Bearer $SCALEWAY_API_KEY"`.
- Każda próba, wybrany model, tryb i przyczyna fallbacku trafiają do
  `backend/dane/llm.jsonl`.
- Odpowiedź „brak wystarczających informacji w bazie wiedzy” (bez cytatów) pada, gdy:
  1. pytanie wskazuje ustawę („ustawa”, „ustawy”, „ustawie”, „ustawę”, „ustawą”, „u.s.c.”;
     `wzorzec_pytania_o_ustawe`), a dokumentu z klucza `ustawa` nie ma w korpusie; uwaga
     `brak_ustawy` to mówi. Dziś ustawa jest w korpusie (`ustawa-sc`), więc ta odmowa nie zachodzi;
  2. pytanie nie pasuje do FAQ (`prog_faq`), a zawiera pojęcie spoza korpusu i FAQ
     (`nieznane_pojecia` w odpowiedzi);
  3. pytanie nie pasuje do FAQ, a najlepszy fragment ma wynik BM25 poniżej `minimalny_wynik` (4,0)
     albo zawiera mniej niż `minimalne_pokrycie` (0,5) pojęć pytania.
- Ścieżka zawęża źródła do dokumentów danej ścieżki i wspólnych (model kompetencji, OSP, ustawa).
- Ustawa o służbie cywilnej: tekst jednolity Dz.U. 2026 poz. 590 z ISAP (stan prawny na
  14.04.2026; strony 1–2 z obwieszczeniem są poza korpusem, `od_strony: 3`). Artykuł wskazany
  w pytaniu („art. 81 ustawy”, „art. 83 ust. 1 u.s.c.”) daje cytaty z tego artykułu, bez FAQ.
  W pozostałych odpowiedziach najwyżej jeden fragment ustawy (`ustawa_maks_z_rankingu: 1`).
- Odpowiedź modelu z cytatem bez pokrycia jest odrzucana i uruchamia fallback.

### Pomiar jakości asystenta

Pomiar używa niezmienianych zestawów `pytania-kontrolne.yaml` oraz
`pytania-parafrazy.yaml` (`uv run pytest tests/test_asystent_formalny.py -s`).
Pełny zestaw testów działa offline, więc tryb z modelem (wymaga klucza Scaleway)
nie jest w nim uruchamiany; poniższa tabela nie przypisuje mu wyniku bez pomiaru.

| Tryb | Pytania kontrolne: dokument i cytat | Parafrazy: dokument i cytat | Odmowy spoza bazy |
|---|---:|---:|---:|
| Ekstrakcyjny | 22/22 | 16/22 | 6/6 kontrolnych, 5/5 parafraz |
| DeepSeek v4 Flash przez Scaleway (`deepseek-v4-flash-0731`) | do pomiaru z kluczem | do pomiaru z kluczem | do pomiaru z kluczem |

Próba jury (`pytania-jury.yaml`, `uv run pytest tests/test_asystent_proba_jury.py -s`): 30 pytań
zadanych tak, jak mógłby je zadać juror, i 15 pytań odłożonych, na których niczego się nie stroi.
Pytanie jest trafione, gdy odpowiedź pochodzi z właściwej pozycji `faq.yaml`, czyli użytkownik
widzi odpowiedź napisaną przez człowieka i jej cytat.

| Stan | Próba 30 pytań | Zestaw odłożony 15 pytań |
|---|---:|---:|
| Przed dopisaniem pozycji (main `1f676b5`) | 5/30 | 1/15 |
| Po dopisaniu pozycji z próby (#53) | 28/30 | 10/15 |

Dwa pytania próby i jedno odłożone czekają na pozycje z gałęzi `53-asystent-jury`. Na serwerze
testowym z modelem (22.11, main `1f676b5`) te same 30 pytań dostało 9 poprawnych odpowiedzi,
10 błędnych i 5 odmów: błędy brały się z dopasowania FAQ i z blokady nieznanych słów, czyli
z etapów przed modelem.

`GET /api/zrodla` pokazuje dokumenty korpusu, duplikat „Rozporządzenie … (4).pdf” (fragment rozporządzenia z 2016 r., nie osobne źródło) i pliki pominięte.

## Logowanie, role i mock QNT

`POST /api/auth/login {"login": "...", "hasło": "demo"}` zwraca token; kolejne zapytania wysyłają `Authorization: Bearer <token>`.

| Konto | Rola | Widzi |
|---|---|---|
| `przelozony1`, `przelozony2` | przełożony | swoich podwładnych (`przelozony_id`) i notatki o nich |
| `hr` | HR/administrator | wszystkich pracowników, bez notatek przełożonego |
| `oceniany` | oceniany | tylko siebie |

- `GET /api/ja`: zalogowany użytkownik i jego rola.
- `GET /api/pracownicy`, `GET /api/pracownicy/{osoba_id}`: pracownicy z mocka QNT według reguł dostępu; poza zakresem 403, brak osoby 404.
- `GET` i `POST /api/pracownicy/{osoba_id}/notatki`: notatki przełożonego o podwładnym; HR i oceniany dostają 403.

Kontrakt jest w `/docs` (OpenAPI). Konta i uprawnienia zmienia się w `konfiguracja/role.yaml`, bez zmian w kodzie.

**Zakres danych osobowych.** Mock QNT zawiera 10 fikcyjnych osób powiązanych z trzema OSP: imię, nazwisko, stanowisko, komórkę, przełożonego i fakty kadrowe potrzebne do wyboru ścieżki oceny i terminów (podstawa i data zatrudnienia, korpus, ostatnia ocena, egzamin, zastępstwo, nieobecności). Nie ma PESEL, adresów ani danych wrażliwych. Pola `scenariusz` i `oczekiwany_arkusz` służą tylko do demo i testów i nie trafiają do odpowiedzi API.

## Stan pokazu (demo)

Na świeżej bazie, przy działającym API:

```bash
PYTHONPATH=kompas-mc/backend/src:kompas-core/src python -m kompas_mc.stan_demo --api http://127.0.0.1:8002
```

Skrypt przez API (te same reguły i rejestr operacji) przygotowuje ocenę okresową Anny Zielińskiej-Demo (P-101) w trakcie: krok 2 zapisany i część I zamknięta, większość wskaźników oceniona z przykładami (jeden poniżej oczekiwań, jeden „brak podstaw”, jeden pusty do kliknięcia na żywo), bez decyzji przełożonego. Samoocena konta `oceniany` jest przekazana z jedną rozbieżnością o 4 poziomy. Do tego jeden cel zatwierdzony i jedna propozycja celu od Anny. Drugie uruchomienie niczego nie zmienia i kończy się kodem 0.

**Od początku (#186).** Na pulpicie przełożonego, w „Do zrobienia”, przy Annie Zielińskiej-Demo (ocena okresowa) i Zofii Szymańskiej-Demo (pierwsza ocena) jest mały przycisk „Demo: rozpocznij od początku” w linii imienia, za plakietką terminu. Pokazują go osoby z polem `demo_od_poczatku` w `qnt.yaml`. Kliknięcie (bez potwierdzenia) wywołuje `POST /api/demo/pracownicy/{osoba_id}/od-poczatku` kasuje dane oceny tej osoby: procesy (kroki, ocenę, rozmowę, wynik, zakończenie), samoocenę, rejestr EZD, przypomnienia, cele, notatki i wpisy dziennika zmian. Zaraz potem otwiera się ekran „Rozpoczęcie oceny” (krok 1) tej osoby (#208). Rejestr operacji zostaje i odnotowuje reset. Dla osoby bez znacznika endpoint zwraca 403.

## Rejestr operacji

Każda zmiana (żądanie inne niż GET), pobranie dokumentu (PDF, CSV), odczyt karty, oceny, notatek i samooceny oraz każda odmowa 401/403 trafia do tabeli `operacje` w bazie aplikacji: czas, użytkownik (login, rola, osoba), stały kod akcji („METODA trasa”) i nazwa czynności dla HR (słownik `ETYKIETY` w `rejestr.py`; test pilnuje, żeby każda rejestrowana trasa ją miała), trasa, obiekt, osoba oceniana, wynik (`ok`, `odmowa`, `blad`), kod HTTP, czas trwania i identyfikator żądania (nagłówek `X-Request-Id`). Wpis powstaje także wtedy, gdy obsługa żądania rzuci wyjątek. Trasy dopisują szczegóły przez `ustaw_szczegoly(request, …)` tylko z listy dozwolonych pól (np. asystent: tryb, dostawca, odrzuceni dostawcy, wynik walidacji cytatów), a osobę ocenianą spoza ścieżki przez `ustaw_osobe`. Treść żądań, odpowiedzi, notatek, pytań i haseł do rejestru nie trafia. Przy logowaniu zapisuje się tylko zadeklarowany login.

- `GET /api/rejestr` (filtry `od`, `do`, `uzytkownik`, `akcja`, `wynik`, `osoba`, stronicowanie) i `GET /api/rejestr.csv` (do 10 000 wpisów, komórki zaczynające się od `=`, `+`, `-`, `@` dostają apostrof) wymagają uprawnienia `rejestr.czytaj`, które ma tylko HR. Ekran: menu HR → „Rejestr operacji”.
- Tylko dopisywanie: triggery SQLite odrzucają `UPDATE` i `DELETE` na `operacje`. To chroni przed pomyłką w kodzie, nie przed administratorem z dostępem do pliku bazy. Integralność kryptograficzną i kopię poza serwerem trzeba dodać we wdrożeniu urzędu.
- Przechowywanie: aplikacja nie usuwa wpisów. Okres przechowywania i usuwanie po jego upływie ustala administrator (RODO art. 5 ust. 1 lit. e). Dla wpisów wywołań AI warto przyjąć co najmniej 6 miesięcy (AI Act art. 26 ust. 6 wymaga tego dla systemów wysokiego ryzyka; kwalifikację systemu ocenia urząd).
- Granica: wpis rejestru i zmiana danych mają osobne transakcje. Zmiana zapisana przy błędzie zapisu rejestru da wynik bez wpisu. Wpis o odmowie albo błędzie powstaje niezależnie od wycofania zmian.

## Krok 1: analiza OSP, ścieżka i arkusz

- `GET /api/pracownicy/{osoba_id}/krok1` (podgląd, akcja `ocena.czytaj`) zwraca OSP z korpusu: cel, zadania dominujące i pozostałe, liczbę podległych, złożoność, samodzielność i kompetencje miękkie. Każde pole ma adnotację z cytatem. Zwraca też propozycję ścieżki z przesłankami i arkusz B/C według § 3 rozp. 2016.
- Przesłanki ustawowe krok 1 bierze z poradników, więc mają kategorię `OBJAŚNIENIE_MATERIAŁU` i uwagę „brak tekstu ustawy w bazie” (zapisaną przed dodaniem ustawy do korpusu; przepięcie na `ustawa-sc` to osobna zmiana). Gdy dane kadrowe są niejednoznaczne, `proponowana` ma wartość `null`, a `braki` mówią, czego brakuje.
- `POST /api/procesy {"osoba_id", "sciezka", "uzasadnienie"?}` (akcja `ocena.prowadz`, tylko przełożony) rozpoczyna proces oceny. Wybór innej ścieżki niż proponowana wymaga uzasadnienia.
- `GET /api/procesy` i `GET /api/procesy/{id}` pokazują procesy według ról.
- Treść reguł (opisy i cytaty) jest w `konfiguracja/krok1.yaml`.

## Krok 2: kryteria i wskaźniki

- `GET /api/model-kompetencji` zwraca model z `Model_kompetencji.xlsx`: 14 kompetencji, 49 wskaźników, 5 poziomów (1/3/5/7/9) i instrukcję. Każdy element ma adnotację z komórką arkusza.
- `GET /api/procesy/{id}/krok2` zwraca kryteria obowiązkowe według arkusza: § 4 ust. 2 (B) i § 4 ust. 3 (C) rozp. 2016 albo § 2 pkt 1 rozp. 2015. Pokazuje też propozycje najwyżej 3 kryteriów dodatkowych (w pierwszej ocenie 0) oraz przy każdym wskaźniku zadania z OSP, które go uzasadniają.
- `PUT /api/procesy/{id}/krok2 {"dodatkowe": [...], "wskazniki": {kompetencja_id: [wskaznik_id]}}` (akcja `ocena.prowadz`) zapisuje wybór przełożonego. Limit dodatkowych sprawdza API.
- `PUT /api/procesy/{id}/krok2/zapoznanie {"data"}` kończy część I arkusza: data rozmowy na początku okresu i zapoznania ocenianego z kryteriami (§ 5 ust. 1, § 6 ust. 2), zapisana w `krok2.zapoznanie`. Nowy zapis kryteriów ją kasuje. 409 przed zapisem kryteriów, 422 dla daty z przyszłości albo sprzed zapisu kryteriów.
- Dobór zadań do wskaźników i punktacja kryteriów dodatkowych to `DECYZJA_PROJEKTOWA` („wymaga zatwierdzenia”). Słowa kluczowe są jawne w `konfiguracja/krok2.yaml`.
- `GET /api/procesy/{id}/arkusz-okresowy/czesc-i/pdf` (akcja `ocena.tresc`) zwraca samą część I arkusza B albo C do podpisu po rozmowie na początku okresu (§ 5 ust. 3 i § 6 rozp. 2016). Wydruk zawiera dane obu stron, kryteria obowiązkowe i dodatkowe, termin sporządzenia oceny z kalendarza terminów oraz miejsca na podpisy i daty. Jest dostępny od zapisu kroku 2, bez wyniku oceny; wcześniej API zwraca 409. Gdy terminu nie da się wyliczyć (np. po ocenie negatywnej brak daty zapoznania z nią), API zwraca 422 z listą `braki_terminu`. Zmiana kryteriów zmienia wydruk i jego odcisk w stopce.

## Kroki 3–5: zachowania, sugestia, decyzja

- `GET /api/procesy/{id}/ocena` zwraca wskaźniki wybrane w kroku 2 z 5 opisami zachowań, oceny i przykłady oraz sugestię poziomu każdego kryterium z etykietą metodyki. Zwraca też decyzję przełożonego i dane w formacie `/api/rozwoj/propozycje`.
- `PUT /api/procesy/{id}/ocena/wskazniki` (krok 3) zapisuje poziom 1/3/5/7/9 albo „brak podstaw do oceny” oraz przykłady w układzie sytuacja – działanie – rezultat (z powtarzalnością, złożonością i uprawnieniami). Poziom inny niż 5 bez przykładu daje ostrzeżenie.
- `PUT /api/procesy/{id}/ocena/decyzje` (krok 5) zapisuje ocenę cząstkową. Punkty muszą być ze skali ścieżki: 1–9 według § 11 rozp. 2016 albo 3/5/7 według § 9 rozp. 2015. Uzasadnienie odejścia od sugestii jest opcjonalne; `zgodna_z_sugestia` zapisuje, czy ocena się różni.
- `PUT /api/procesy/{id}/ocena/rozmowa` zapisuje rozmowę oceniającą (§ 10 rozp. 2016): notatki tematów (`obowiazki`, `sprawozdanie`, `cele`, `rozwoj`), szkic informacji zwrotnej i datę rozmowy do części II arkusza; odczyt w polu `rozmowa` odpowiedzi `GET …/ocena`. Data z przyszłości albo sprzed zapoznania z kryteriami daje 422. Data przy komplecie ocen cząstkowych kończy rozmowę: proces przechodzi do oceny na piśmie (krok 6).
- Metodyka sugestii (`konfiguracja/ocena.yaml`, `DECYZJA_PROJEKTOWA`):
  - mediana ocenionych wskaźników;
  - „brak podstaw” nie wchodzi do mediany;
  - przy remisie system pokazuje dwie wartości;
  - poniżej połowy ocenionych wskaźników sugestii nie ma („niewystarczające dane”);
  - w pierwszej ocenie mapowanie 5→3.

  Sugestia nigdy nie wpisuje oceny sama.

## Cele rozwojowe

Cele należą do pracownika, nie do procesu oceny. Cel ma nazwę, opis, opcjonalny wskaźnik z modelu kompetencji, miernik, termin i status: `propozycja` → `zatwierdzony` → `w_realizacji` → `osiągnięty` albo `porzucony`. Odrzucona propozycja ma status `odrzucony` i komentarz przełożonego. Każda zmiana trafia do dziennika zmian.

Przełącznik `pracownik_moze_edytowac` w `konfiguracja/cele.yaml`:

- `true`: pracownik tworzy i zmienia cele, a zmiana treści przywraca `propozycja`;
- `false`: cele tworzy i zmienia tylko przełożony.

W obu trybach cel zatwierdza przełożony. Pracownik ustawia `w_realizacji` i zgłasza osiągnięcie, a status `osiągnięty` potwierdza przełożony. Uprawnienia w `role.yaml`: `cele.czytaj` (przełożony, pracownik, HR), `cele.proponuj` (przełożony, pracownik), `cele.zatwierdz` (przełożony).

- `GET /api/pracownicy/{osoba_id}/cele` zwraca cele osoby i wartość przełącznika.
- `POST /api/pracownicy/{osoba_id}/cele {"nazwa", "opis", "wskaznik_id"?, "miernik", "termin"}` tworzy cel ze statusem `propozycja` (201). Pracownik przy `false` dostaje 403, a wskaźnik spoza modelu daje 422.
- `PUT /api/cele/{id}` zmienia treść. Zmiana przez pracownika przywraca `propozycja`; zmiana przez przełożonego zostawia status. Odrzucony cel po zapisie (także bez zmian) wraca jako `propozycja` z komentarzem przełożonego. Cel `osiągnięty` albo `porzucony`: 409.
- `POST /api/cele/{id}/zatwierdz` (przełożony, tylko z `propozycja`).
- `POST /api/cele/{id}/odrzuc {"komentarz"}` (przełożony, tylko z `propozycja`). Pusty komentarz: 422.
- `POST /api/cele/{id}/status {"status": "w_realizacji" | "osiągnięty" | "porzucony"}`. `w_realizacji` tylko z `zatwierdzony`. `osiągnięty` od pracownika ustawia `zgloszono_osiagniecie`, a od przełożonego zmienia status. `porzucony` ustawia przełożony przy celu zatwierdzonym albo w realizacji.
- `GET /api/cele/{id}/historia` zwraca dziennik zmian celu.
- `GET /api/pracownicy/{osoba_id}/cele/podpowiedzi` zwraca propozycje celów ze wskaźników ocenionych poniżej 5 w ostatnim procesie (reguły z `rozwoj.yaml`). Podpowiedzi mają status `propozycja` i niczego nie zapisują. Pracownik widzi podpowiedzi z oceny w toku dopiero po przekazaniu samooceny.

### Podpowiedzi celów z LLM i RAG

Endpoint podpowiedzi najpierw pyta LLM (łańcuch z `asystent.yaml` bez dostawcy ekstrakcyjnego, ustawienia w `cele.yaml`, sekcja `llm`). Model dostaje:

- fragmenty `Model_kompetencji.xlsx` dla ocenionych wskaźników (wskaźnik i opisy poziomów);
- strony poradników o wnioskach rozwojowych i IPRZ (`llm.zrodla`);
- pseudonimizowany kontekst: wskaźniki z ostatniego procesu, samoocenę po przekazaniu i istniejące cele. Imię, nazwisko, komórka ani identyfikator osoby nie trafiają do modelu.

Model zwraca 1–3 cele SMART: nazwę, opis, miernik, termin, wskaźnik modelu i cytat. Cel ze wskaźnikiem spoza modelu albo z cytatem bez pokrycia w podanym fragmencie jest odrzucany, a powód trafia do pola `odrzucone`. Gdy LLM zawiedzie (np. brak `SCALEWAY_API_KEY`) albo żaden cel nie przejdzie walidacji, API zwraca podpowiedzi regułowe (`zrodlo: "reguly"`). Każda podpowiedź ma status `propozycja`, oznaczenie „Sugestia asystenta – do edycji” i nigdy nie zapisuje się sama.

Zakazane przejście zwraca 409, a akcja spoza roli 403.

## Testy i walidator

```sh
cd kompas-mc/backend
uv run pytest -q
uv run kompas-waliduj --manifest ../konfiguracja/korpus.yaml ../konfiguracja/*.yaml
```

Walidator sprawdza każdy element konfiguracji z kluczem `adnotacje`: czy ma
adnotację i czy cytat występuje dosłownie w korpusie; przy błędzie kończy się
kodem 1. Repo nie ma CI: testy i walidator uruchamia się ręcznie.

## Dodanie lub podmiana dokumentu w bazie wiedzy

Bazy wiedzy nie tworzy model: przy każdym starcie API kod czyta pliki z manifestu
(PDF z warstwą tekstową, DOCX, XLSX; skan bez tekstu dostaje status `BRAK_TEKSTU`).

1. Plik do `materialy mc/`.
2. Wpis w `konfiguracja/korpus.yaml`: `doc_id`, `doc_version` (np. rok albo data aktu),
   `nazwa`, `plik`, `sciezka`, `kategoria`, `podzial` (opis pól w nagłówku pliku). Przy podmianie
   zmień `doc_version`.
3. Restart API (`uv run kompas-mc`). Gdy cytatu z `faq.yaml` nie ma w nowym tekście,
   API nie wstaje i podaje identyfikator pozycji FAQ.
4. Walidator: `uv run kompas-waliduj --manifest ../konfiguracja/korpus.yaml ../konfiguracja/*.yaml`,
   wynik 0 błędów.
5. Testy asystenta: `uv run pytest tests/test_asystent_formalny.py -s`; zestaw kontrolny
   22/22, parafrazy i odmowy nie gorzej niż w tabeli wyżej. Nowe słownictwo zmienia
   progi (`minimalny_wynik`, `minimalne_pokrycie`, `prog_faq`), więc mierzy się je od nowa.
6. Panel Źródła (konto `hr`): dokument na liście ze statusem ekstrakcji `OK`.

Test `test_kazdy_plik_z_materialow_jest_uwzgledniony` (`tests/test_izolacja.py`) pilnuje,
żeby każdy plik z `materialy mc/` był źródłem, duplikatem albo świadomie pominięty.
