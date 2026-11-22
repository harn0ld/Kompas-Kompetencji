# Prezentacja – plan 10 slajdów

Logika: problem → zasady → ścieżka (demo) → AI → HR i dokumenty → architektura → rozwój.

1. **Kompas Kompetencji.** Przełożony w służbie cywilnej przechodzi ocenę krok po kroku. Każda informacja ma źródło, a decyzja zawsze należy do niego.
2. **Problem.** Przepisy, model kompetencji, OSP, formularz i terminy leżą w różnych miejscach. Ocena „z wrażenia” zamiast z zachowań daje różne interpretacje u różnych przełożonych.
3. **Trzy zasady.** (1) Źródło przy każdej informacji: 231 cytatów sprawdzanych walidatorem, 0 błędów. (2) Decyduje przełożony: sugestie nigdy nie wpisują oceny. (3) AI odpowiada tylko z bazy albo mówi „brak informacji”.
4. **Ścieżka oceny okresowej, kroki 1–2.** OSP → ścieżka i arkusz B/C z przesłankami → kryteria obowiązkowe i do 3 dodatkowych → wskaźniki uzasadnione zadaniami z OSP. Zrzut ekranu.
5. **Kroki 3–5: model kompetencji w praktyce.** Wybór opisu zachowania i przykład S-D-R → sugerowany poziom (mediana, remis bez wyboru, „brak podstaw” nie obniża) → decyzja przełożonego; uzasadnienie odejścia od sugestii można dopisać (opcjonalne). Zrzut ekranu.
6. **Asystent formalny.** Pytanie → odpowiedź z cytatem, dokumentem i paragrafem. Pytanie spoza bazy → „brak wystarczających informacji”. Pytanie o artykuł ustawy (np. „art. 83 ustawy”) → cytat z tekstu jednolitego Dz.U. 2026 poz. 590. Łańcuch dostawców z `asystent.yaml` (DeepSeek v4 Flash przez Scaleway w UE → Ollama → ekstrakcyjny) z walidacją cytatów; na ekranie tylko zweryfikowane cytaty. Zrzut ekranu.
7. **Rozmowa, wynik i wnioski (kroki 6–8).** Plan rozmowy z pytaniami powiązanymi ze wskaźnikami i przykładami. Wynik § 11 z regułą rozstrzygającą. Arkusz B/C → PDF → EZD. Propozycje form rozwoju do IPRZ.
8. **HR i transparentność.** Panel procesów z filtrem „zagrożone” i przypomnieniami. Panel źródeł z brakami, rozbieżnościami i pytaniami do mentorów. Wersje metodyki zatwierdzane z osobą i datą.
9. **Architektura i bezpieczeństwo.** Core bez treści i konfiguracja YAML z cytatami, API z OpenAPI, role egzekwowane w API, dziennik zmian, mocki QNT/EZD, łańcuch dostawców AI z walidacją cytatów i pseudonimizacją kontekstu. Schemat z `architektura.md`.
10. **Wdrożenie i rozwój.** Lista zabezpieczeń przed produkcją (SSO, szyfrowanie, prawdziwe QNT/EZD, model w infrastrukturze MC, aktualizacja ustawy po zmianie od 1.01.2027). Kolejne kroki: inne urzędy, aktualizacja przepisów z zatwierdzaniem (plan rozwoju bazy wiedzy w `architektura.md`), statystyki kompetencji dla HR.

Zrzuty ekranu dołączamy po próbie demo (#40). Każdy pokazuje dane fikcyjne.
