# Kompas Kompetencji – opis projektu

## Koncepcja

Kompas Kompetencji prowadzi przełożonego w służbie cywilnej krok po kroku przez **pierwszą ocenę** albo **ocenę okresową**. Łączy w jednym miejscu przepisy, model kompetencji, opis stanowiska pracy, formularz i asystenta AI.

Działamy według trzech zasad:

1. **Każda informacja ma źródło.** Reguła, kryterium, termin i odpowiedź asystenta wskazują dokument, paragraf lub komórkę i dosłowny cytat. Walidator `kompas-waliduj` sprawdza, że każdy cytat występuje w materiałach MC (231 cytatów, 0 błędów). Gdy materiałów brakuje albo przeczą sobie nawzajem, aplikacja mówi to wprost.
2. **Decyzję podejmuje przełożony.** System proponuje poziom kompetencji, kryteria dodatkowe, pytania do rozmowy i formy rozwoju. Nigdy nie wpisuje oceny ani treści dokumentu.
3. **AI odpowiada tylko z bazy wiedzy.** Asystent formalny cytuje przepisy i poradniki. Na pytanie spoza bazy odpowiada „brak wystarczających informacji w bazie wiedzy”. Ustawę o służbie cywilnej cytuje z tekstu jednolitego (Dz.U. 2026 poz. 590, stan prawny na 14.04.2026), także artykuł wskazany w pytaniu.

## Ścieżka przełożonego (ocena okresowa)

| Krok | Co robi przełożony | Co robi system |
|---|---|---|
| 1. Analiza OSP | Otwiera ocenę pracownika z listy podwładnych | Analizuje opis stanowiska (cel, zadania, liczba podległych). Proponuje ścieżkę (pierwsza/okresowa) i arkusz B albo C, z przesłankami i cytatami. Przy brakach danych pokazuje listę braków i nie zgaduje. |
| 2. Kryteria i wskaźniki | Zatwierdza kryteria obowiązkowe, wybiera do 3 dodatkowych i wskaźniki | Ładuje kryteria obowiązkowe arkusza (§ 4) i proponuje dodatkowe z zadań OSP. Przy każdym wskaźniku pokazuje zadania, które go uzasadniają. Czwartego kryterium API nie przyjmie. |
| 3. Zachowania i przykłady | Przy każdym wskaźniku wybiera opis zachowania (5 poziomów z modelu) albo „brak podstaw” i dodaje przykład: sytuacja – działanie – rezultat | Ostrzega, gdy poziom inny niż „na poziomie oczekiwań” nie ma przykładu. |
| 4. Sugerowany poziom | Widzi sugestię dla kryterium | Liczy medianę poziomów wskaźników według zatwierdzonej wersji metodyki. „Brak podstaw” nie obniża sugestii. Przy remisie pokazuje obie wartości i nie wybiera. |
| 5. Decyzja | Sam wybiera ocenę cząstkową | Zapisuje, czy decyzja odbiega od sugestii; uzasadnienie opcjonalne. |
| 6. Rozmowa i wynik | Przygotowuje rozmowę, wpisuje daty i uzasadnienie | Asystent rozmowy daje plan: zakres z przepisu, pytania z powiązaniem i uzasadnieniem, argumenty, szkic informacji zwrotnej. Wynik według § 11: średnia, poziom, reguła rozstrzygająca (np. jedna ocena 1 pkt ⇒ negatywna). Terminy liczy kalendarz, zawiadomienie § 8 trafia do PDF. |
| 7. Formularz i PDF | Uzupełnia brakujące pola, zatwierdza | Wypełnia arkusz B/C danymi z procesu i kadr, blokuje PDF przy brakach, generuje PDF do podpisu odręcznego i rejestruje go w (mockowym) EZD. |
| 8. Wnioski rozwojowe | Pisze wnioski do IPRZ | Proponuje obszary rozwoju (wskaźniki poniżej oczekiwań) i mocne strony z formami rozwoju z poradników. Wiąże każdą propozycję ze wskaźnikiem i przykładem. |

Ścieżka **pierwszej oceny** (rozporządzenie z 2015 r.) to osobny proces z własnymi zasadami:
- skala 3/5/7 i mapowanie poziomów modelu 5→3 widoczne przy sugestii;
- terminy (rozmowa wstępna w 21 dni, sprawozdanie, okno oceny z przedłużeniem o nieobecność);
- wynik według § 10 ust. 1, np. łączna 5,0 przy dwóch ocenach 3 pkt daje ocenę negatywną, a sprawozdanie po terminie daje ocenę negatywną niezależnie od ocen;
- arkusz pierwszej oceny z PDF;
- wnioski rozwojowe tylko przy ocenie pozytywnej.

## Najważniejsze funkcje

- **Asystent formalny** (czat): odpowiada z przepisów, poradników, modelu kompetencji i zestawu pytań i odpowiedzi drużyny, z dokumentem, paragrafem i stroną. Filtruje źródła według ścieżki oceny.
- **Model kompetencji**: 14 kompetencji, 49 wskaźników, 5 poziomów. Nazwy wskaźników są zgodne z zał. 1 obu rozporządzeń, co sprawdza test.
- **Panel HR/administratora**: statusy procesów, terminy, filtr „zagrożone” (termin ≤ 7 dni), przypomnienia ze skrzynką nadawczą i historią. HR nie widzi treści ocen ani notatek.
- **Panel źródeł i braków**: inwentarz materiałów, braki (np. ustawa, arkusz A), rozbieżności (np. skala 5 a 3, brak kroku OSP na grafice pierwszej oceny) i pytania do mentorów MC.
- **Wersjonowana metodyka**: sugestię i mapowanie 5→3 zatwierdza HR z osobą i datą. Ocena zapamiętuje wersję, według której ją liczono.
- **Konta demo i role**: przełożony, HR/administrator, oceniany. Uprawnienia egzekwuje API, a każda zmiana trafia do dziennika.

## Dane demo

Pracownicy z mocka QNT są fikcyjni. Opisy stanowisk pochodzą z trzech OSP z materiałów MC. Te OSP są z dwóch departamentów, więc w demo przełożona (Departament Rozwoju i Bezpieczeństwa SI) ocenia też naczelnika z Departamentu Współpracy Międzynarodowej; w urzędzie oceniającym jest zawsze bezpośredni przełożony z komórki ocenianego. Konta demo: `przelozony1`, `przelozony2`, `hr`, `oceniany` (hasło `demo`).
