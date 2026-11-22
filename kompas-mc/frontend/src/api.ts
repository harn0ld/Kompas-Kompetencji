export type Sciezka = "pierwsza" | "okresowa";

export interface CytatAsystenta {
  fragment_id: string;
  doc_id: string;
  dokument: string;
  lokalizator: string | null;
  strona: number | null;
  kategoria: string;
  cytat: string;
  /** Najlepiej pasujące zdanie: dosłowny podciąg `cytat`. */
  wyrozniony: string | null;
  /** Objaśnienie powołuje ustawę, której tekstu nie ma w bazie wiedzy. */
  powoluje_ustawe: boolean;
}

export interface OdpowiedzAsystenta {
  pytanie: string;
  sciezka: Sciezka | null;
  znaleziono: boolean;
  komunikat: string | null;
  tresc: string | null;
  cytaty: CytatAsystenta[];
  tryb: "NA_ŻYWO" | "ZAPISANE" | "EKSTRAKCYJNE" | null;
  dostawca: string | null;
  odrzuceni: string[];
  pokrycie: number;
  /** Pozycja z przygotowanego zestawu pytań i odpowiedzi (faq.yaml), jeśli z niej odpowiedź. */
  faq_id: string | null;
  /** Treść przepisana prostym językiem przez model na prośbę „prościej”. */
  uproszczona?: boolean;
  nieznane_pojecia: string[];
  uwagi: string[];
}

export interface Zrodla {
  dokumenty: { doc_id: string; nazwa: string; sciezka: string; kategoria: string; w_asystencie: boolean; status: string; fragmenty: number }[];
  duplikaty: { plik: string; duplikat_z: string; pokrycie: number; potwierdzony: boolean }[];
  pominiete: { plik: string; powod: string }[];
}

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r.json() as Promise<T>;
}

export const pobierzZrodla = () => fetch("/api/zrodla").then((r) => json<Zrodla>(r));

/** Klucz sesji w sessionStorage (App). Asystent czyta stąd token, bez przekazywania go przez komponenty. */
export const KLUCZ_SESJI = "kompas-mc-sesja";
const tokenSesji = () => (JSON.parse(sessionStorage.getItem(KLUCZ_SESJI) ?? "null") as { token?: string } | null)?.token ?? "";

/** `poprzednie`: ostatnie pytanie z okna asystenta, żeby dopytanie („a prościej?”) miało do czego się odnieść. */
export const pytajAsystenta = (pytanie: string, sciezka: Sciezka | null, poprzednie?: string) =>
  fetch("/api/asystent", {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(tokenSesji()) },
    body: JSON.stringify({ pytanie, sciezka, poprzednie: poprzednie ?? null }),
  }).then((r) => json<OdpowiedzAsystenta>(r));

export type Rola = "przelozony" | "hr" | "oceniany";

export interface Uzytkownik {
  login: string;
  rola: Rola;
  osoba_id: string | null;
}

export interface Pracownik {
  osoba_id: string;
  imie: string;
  nazwisko: string;
  stanowisko: string;
  symbol_osp: string | null;
  komorka: string;
  przelozony_id: string;
  kieruje_pracownikami: boolean;
  korpus: "urzednik_sc" | "pracownik_sc";
  data_zatrudnienia: string;
  rodzaj_umowy: "nieokreslony" | "okreslony";
  ostatnia_ocena_okresowa: { data: string; wynik: "pozytywna" | "negatywna" } | null;
  data_konca_zatrudnienia?: string | null;
  zmiana_oceniajacego?: { data: string; poprzedni_przelozony: string } | null;
  pierwsza_ocena?: {
    egzamin_sluzba_przygotowawcza: "zaliczony" | "nie_dotyczy" | "brak";
    rozmowa_wstepna: string | null;
    uzgodnienie_zastepstwa: string | null;
  } | null;
  absolwent_ksap?: boolean;
  wniosek_o_mianowanie?: boolean | null;
  zastepstwo?: boolean;
  nieobecnosci?: { od: string; do: string; rodzaj: string }[];
  /** Osoba demo z przyciskiem „Rozpocznij od początku” (#186): którą ocenę testujemy. */
  demo_od_poczatku?: "okresowa" | "pierwsza" | null;
}

const autoryzacja = (token: string) => ({ authorization: `Bearer ${token}` });

export const zaloguj = (login: string, haslo: string) =>
  fetch("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ login, hasło: haslo }),
  }).then((r) => json<{ token: string }>(r));

export const pobierzJa = (token: string) =>
  fetch("/api/ja", { headers: autoryzacja(token) }).then((r) => json<Uzytkownik>(r));

export const pobierzPracownikow = (token: string) =>
  fetch("/api/pracownicy", { headers: autoryzacja(token) }).then((r) => json<Pracownik[]>(r));

export interface SourceRef {
  doc_id?: string | null;
  lokalizator?: string | null;
  strona?: number | null;
  "cytat_dosłowny"?: string | null;
  kategoria: string;
  uzasadnienie?: string | null;
  "zatwierdził"?: string | null;
}

export interface PanelBrakow {
  braki: {
    id: string;
    typ: "BRAK" | "ROZBIEŻNOŚĆ" | "DUPLIKAT";
    tytul: string;
    opis: string;
    wplyw: string | null;
    pliki: string[];
    adnotacje: { adnotacja: SourceRef; dokument: string | null; plik: string | null; cytat_w_korpusie: boolean | null }[];
    rozbieznosc: { opis: string; zastosowana: number | null; uzasadnienie: string | null } | null;
  }[];
  pytania_do_mentorow: { id: string; dotyczy: string; pytanie: string }[];
}

/** Panel źródeł i braków: tylko rola HR/administrator. */
export const pobierzBraki = (token: string) =>
  fetch("/api/braki", { headers: autoryzacja(token) }).then((r) => json<PanelBrakow>(r));

/* Krok 1 i proces oceny (#29, kontrakt w issue #29). */

export interface Pole {
  tekst: string;
  adnotacja: SourceRef;
}

export interface Brak {
  pole: string;
  komunikat: string;
}

export interface Przeslanka {
  id: string;
  sciezka: Sciezka;
  opis: string;
  spelniona: boolean | null;
  dane_kadrowe: Record<string, unknown>;
  adnotacje: SourceRef[];
  uwaga: string | null;
}

export interface UwagaKroku {
  id: string;
  komunikat: string;
  adnotacje: SourceRef[];
}

export interface Osp {
  doc_id: string;
  symbol: string;
  nazwa: string;
  komorka: string[];
  cel: Pole;
  zadania_dominujace: (Pole & { nr: number })[];
  zadania_pozostale: (Pole & { nr: number })[];
  podlegli: { zaznaczone: string; kieruje: boolean; adnotacja: SourceRef };
  zlozonosc: { opis: Pole; przyklady: Pole | null };
  samodzielnosc: { opis: Pole; przyklady: Pole | null };
  kompetencje_miekkie: { lista: string[]; adnotacja: SourceRef };
}

export interface AnalizaKroku1 {
  osoba_id: string;
  osp: Osp | null;
  sciezka: { proponowana: Sciezka | null; przeslanki: Przeslanka[]; braki: Brak[] };
  arkusz_okresowy: {
    arkusz: "B" | "C" | null;
    zrodlo: "OSP" | "QNT";
    uzasadnienie: string;
    adnotacje: SourceRef[];
    braki: Brak[];
  };
  arkusz_a: { status: string; dotyczy: boolean; komunikat: string; adnotacje: SourceRef[] };
  uwagi: UwagaKroku[];
}

export interface ProcesOceny {
  id: number;
  osoba_id: string;
  sciezka: Sciezka;
  arkusz: "B" | "C" | "PIERWSZA";
  krok: number;
  status: string;
  rozpoczal: string;
  rozpoczeto: string;
  zgodna_z_propozycja: boolean;
  uzasadnienie: string | null;
  /** Kryteria zatwierdzone w kroku 2 (z datą zapoznania, gdy część I jest zakończona); null przed zapisem. */
  krok2?: WyborKroku2 | null;
}

/** Błąd API z kodem i polem `detail` (np. braki przy 422). */
export class BladApi extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(`API ${status}`);
  }
}

export const pobierzKrok1 = (token: string, osobaId: string) =>
  fetch(`/api/pracownicy/${encodeURIComponent(osobaId)}/krok1`, { headers: autoryzacja(token) }).then((r) =>
    json<AnalizaKroku1>(r),
  );

export const pobierzProcesy = (token: string) =>
  fetch("/api/procesy", { headers: autoryzacja(token) }).then((r) => json<ProcesOceny[]>(r));

/** Najbliższy termin procesu (te same wiersze co panel HR, bez treści ocen). */
export interface TerminProcesu {
  proces_id: number;
  osoba_id: string;
  osoba: string;
  sciezka: Sciezka;
  krok: number;
  status: string;
  najblizszy_termin: { nazwa: string; data: string; adnotacje: SourceRef[] } | null;
  dni_do_terminu: number | null;
  zagrozony: boolean;
}

export const pobierzTerminy = (token: string) =>
  fetch("/api/terminy", { headers: autoryzacja(token) }).then((r) => json<TerminProcesu[]>(r));

export interface Notatka {
  id: number;
  osoba_id: string;
  autor: string;
  tresc: string;
  czas: string;
}

export const pobierzNotatki = (token: string, osobaId: string) =>
  fetch(`/api/pracownicy/${encodeURIComponent(osobaId)}/notatki`, { headers: autoryzacja(token) }).then((r) =>
    json<Notatka[]>(r),
  );

export async function rozpocznijProces(
  token: string,
  dane: { osoba_id: string; sciezka: Sciezka; uzasadnienie: string | null },
): Promise<ProcesOceny> {
  const r = await fetch("/api/procesy", {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify(dane),
  });
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as ProcesOceny;
}

/* Krok 2: kryteria i wskaźniki (#30, kontrakt w issue #30). */

export interface Instrukcja {
  tekst: string;
  adnotacja: SourceRef;
}

export interface ZadanieWskaznika {
  nr: number;
  rodzaj: "DOMINUJACE" | "POZOSTALE";
  tekst: string;
  slowa: string[];
  adnotacja: SourceRef;
}

export interface WskaznikKroku2 {
  wskaznik_id: string;
  nazwa: string;
  proponowany: boolean;
  podstawa: SourceRef;
  zadania: ZadanieWskaznika[];
}

export interface KryteriumKroku2 {
  kompetencja_id: string;
  nazwa: string;
  rodzaj: "OBOWIAZKOWE" | "DODATKOWE_PROPONOWANE" | "DODATKOWE_DOSTEPNE" | "NIEDOSTEPNE";
  propozycja?: { punkty: number; powody: string[]; adnotacje: SourceRef[] } | null;
  wskazniki: WskaznikKroku2[];
}

export interface WyborKroku2 {
  kryteria: {
    kompetencja_id: string;
    nazwa: string;
    rodzaj: "OBOWIAZKOWE" | "DODATKOWE";
    wskazniki: { id: string; nazwa: string }[];
  }[];
  zapisal: string;
  zapisano: string;
  /** Data rozmowy i zapoznania z kryteriami (§ 6 ust. 2): zakończenie części I. */
  zapoznanie?: string | null;
  /** Oczekiwania i cele na okres (§ 5 ust. 1 pkt 3–4), cel w wierszu. */
  ustalenia?: string | null;
}

export interface Krok2 {
  proces_id: number;
  sciezka: Sciezka;
  arkusz: "B" | "C" | "PIERWSZA";
  limit_dodatkowych: number;
  podstawa_obowiazkowych: SourceRef[];
  podstawa_dodatkowych: SourceRef[];
  metodyka: { id: string; status: string; opis: string; adnotacje: SourceRef[] };
  instrukcja: Instrukcja[];
  kryteria: KryteriumKroku2[];
  wybor: WyborKroku2 | null;
}

export const pobierzKrok2 = (token: string, procesId: number) =>
  fetch(`/api/procesy/${procesId}/krok2`, { headers: autoryzacja(token) }).then((r) => json<Krok2>(r));

export async function zapiszKrok2(
  token: string,
  procesId: number,
  dane: { dodatkowe: string[]; wskazniki: Record<string, string[]> },
): Promise<ProcesOceny> {
  const r = await fetch(`/api/procesy/${procesId}/krok2`, {
    method: "PUT",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify(dane),
  });
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as ProcesOceny;
}

/** Zakończenie części I: data rozmowy na początku okresu i zapoznania z kryteriami (§ 5 ust. 1, § 6 ust. 2). */
export async function zapiszZapoznanie(token: string, procesId: number, data: string, ustalenia?: string): Promise<ProcesOceny> {
  const r = await fetch(`/api/procesy/${procesId}/krok2/zapoznanie`, {
    method: "PUT",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify({ data, ustalenia: ustalenia?.trim() || null }),
  });
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as ProcesOceny;
}

/* Kroki 3–5: zachowania i przykłady, sugestia, decyzja przełożonego (#31, kontrakt w issue #31). */

export interface Przyklad {
  sytuacja: string;
  dzialanie: string;
  rezultat: string;
  powtarzalnosc: "JEDNORAZOWE" | "KILKAKROTNE" | "REGULARNE" | null;
  zlozonosc: "NISKA" | "SREDNIA" | "WYSOKA" | null;
  uprawnienia: string | null;
}

export interface OcenaWskaznika {
  poziom: number | null;
  brak_podstaw: boolean;
  przyklady: Przyklad[];
  /** Uwagi z rozmowy przy wskaźniku (zamiast pełnego przykładu). */
  uwagi?: string | null;
}

export interface WskaznikOceny {
  wskaznik_id: string;
  nazwa: string;
  poziomy: { poziom: number; etykieta: string; opis: string }[];
  ocena: OcenaWskaznika | null;
  ostrzezenia: string[];
  /** Samoocena pracownika (#8): tylko dla przełożonego i tylko po przekazaniu. */
  samoocena?: { poziom: number | null; brak_zdania: boolean; przyklad: PrzykladSamooceny | null } | null;
  /** |samoocena − ocena przełożonego| ≥ 4; null, gdy brak obu poziomów. */
  rozbieznosc?: boolean | null;
}

export interface Sugestia {
  status: "POZIOM" | "REMIS" | "NIEWYSTARCZAJACE_DANE";
  poziom_modelu: number | null;
  remis: number[] | null;
  punkty: number | null;
  punkty_remisu: number[] | null;
  rozklad: Record<string, number>;
  oceniono: number;
  wybrano: number;
  opis: string;
  metodyka: string;
}

export interface Decyzja {
  punkty: number;
  uzasadnienie: string | null;
  zgodna_z_sugestia: boolean | null;
  zapisal: string;
  zapisano: string;
}

export interface KryteriumOceny {
  kompetencja_id: string;
  nazwa: string;
  rodzaj: "OBOWIAZKOWE" | "DODATKOWE";
  wskazniki: WskaznikOceny[];
  sugestia: Sugestia;
  decyzja: Decyzja | null;
}

export type TematRozmowy = "obowiazki" | "sprawozdanie" | "cele" | "rozwoj";

/** Zapis rozmowy oceniającej (§ 10): notatki tematów, szkic informacji zwrotnej, data do części II arkusza. */
export interface ZapisRozmowy {
  data?: string | null;
  notatki?: Partial<Record<TematRozmowy, string>>;
  mocne_strony?: string | null;
  obszary_rozwoju?: string | null;
}

export interface StanOceny {
  /** Status samooceny (#8), tylko dla przełożonego. */
  samoocena_status?: StatusSamooceny | null;
  rozmowa?: ZapisRozmowy | null;
  proces_id: number;
  sciezka: Sciezka;
  arkusz: "B" | "C" | "PIERWSZA";
  skala: { punkty: number[]; etykiety: Record<string, string>; adnotacje: SourceRef[] };
  metodyka: { id: string; status: string; opis: string; adnotacje: SourceRef[] };
  instrukcja: Instrukcja[];
  kryteria: KryteriumOceny[];
  kompletnosc: { wskazniki_ocenione: number; wskazniki_wybrane: number; kryteria_z_decyzja: number; kryteria: number };
  ostrzezenia: string[];
}

/* Samoocena pracownika (#8, #9). Nie wpływa na sugestię ani na ocenę. */

export type StatusSamooceny = "brak" | "szkic" | "przekazana";

export interface PrzykladSamooceny {
  sytuacja: string;
  dzialanie: string;
  rezultat: string;
}

export interface PozycjaSamooceny {
  poziom: number | null;
  brak_zdania: boolean;
  przyklad: PrzykladSamooceny | null;
}

export interface WskaznikSamooceny {
  wskaznik_id: string;
  nazwa: string;
  kompetencja_id: string;
  kryterium: string;
  poziomy: { poziom: number; etykieta: string; opis: string }[];
  pozycja: PozycjaSamooceny | null;
}

export interface Samoocena {
  proces_id: number;
  status: StatusSamooceny;
  przekazano: string | null;
  tresc_widoczna: boolean;
  wskazniki: WskaznikSamooceny[];
  wypelniono: number;
  wybrano: number;
  regula: { id: string; opis: string; adnotacje: SourceRef[] };
}

const sciezkaSamooceny = (procesId: number) => `/api/procesy/${procesId}/samoocena`;

export const pobierzSamoocene = (token: string, procesId: number) =>
  fetch(sciezkaSamooceny(procesId), { headers: autoryzacja(token) }).then((r) => odpowiedzApi<Samoocena>(r));

export const zapiszSamoocene = (token: string, procesId: number, wskazniki: Record<string, PozycjaSamooceny | null>) =>
  fetch(sciezkaSamooceny(procesId), {
    method: "PUT",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify({ wskazniki }),
  }).then((r) => odpowiedzApi<Samoocena>(r));

export const przekazSamoocene = (token: string, procesId: number) =>
  fetch(`${sciezkaSamooceny(procesId)}/przekaz`, { method: "POST", headers: autoryzacja(token) }).then((r) =>
    odpowiedzApi<Samoocena>(r),
  );

async function odpowiedzApi<T>(r: Response): Promise<T> {
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as T;
}

/** Poprzednia ocena okresowa z punktami z arkusza w aktach osobowych (§ 12 ust. 2); tylko z ocena.tresc. */
export interface PoprzedniaOcenaOkresowa {
  data: string;
  wynik: "pozytywna" | "negatywna";
  punkty: Record<string, number>;
}

export const pobierzPoprzedniaOcene = (token: string, osobaId: string) =>
  fetch(`/api/pracownicy/${osobaId}/poprzednia-ocena`, { headers: autoryzacja(token) }).then((r) =>
    odpowiedzApi<PoprzedniaOcenaOkresowa | null>(r),
  );

/** Nazwy kompetencji z Model_kompetencji.xlsx (pozostałe pola modelu nie są tu potrzebne). */
export const pobierzModelKompetencji = (token: string) =>
  fetch("/api/model-kompetencji", { headers: autoryzacja(token) }).then((r) =>
    odpowiedzApi<{ kompetencje: { id: string; nazwa: string }[] }>(r),
  );

/** Opis osoby na karcie (#55): zdania z podstawą w faktach; nic się nie zapisuje. */
export interface FaktOpisu {
  id: string;
  tekst: string;
  zrodlo: string;
}
export interface OpisOsoby {
  zdania: { tekst: string; fakty: FaktOpisu[] }[];
  /** "SZABLON" bez modelu, inaczej tryb dostawcy z łańcucha. */
  tryb: string;
  dostawca: string | null;
  oznaczenie: string;
  odrzucone: string[];
}
export const pobierzOpisOsoby = (token: string, osobaId: string, model: boolean) =>
  fetch(`/api/pracownicy/${encodeURIComponent(osobaId)}/opis?model=${model}`, { headers: autoryzacja(token) }).then((r) =>
    odpowiedzApi<OpisOsoby>(r),
  );

/** Błąd niesie kod i komunikat z API (np. 403 dla pracownika przed przekazaniem samooceny). */
export const pobierzOcene = (token: string, procesId: number) =>
  fetch(`/api/procesy/${procesId}/ocena`, { headers: autoryzacja(token) }).then((r) => odpowiedzApi<StanOceny>(r));

async function zapiszOcene(token: string, procesId: number, sciezka: string, dane: object): Promise<StanOceny> {
  const r = await fetch(`/api/procesy/${procesId}/ocena/${sciezka}`, {
    method: "PUT",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify(dane),
  });
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as StanOceny;
}

export const zapiszWskazniki = (token: string, procesId: number, wskazniki: Record<string, OcenaWskaznika | null>) =>
  zapiszOcene(token, procesId, "wskazniki", { wskazniki });

/** Pytanie do rozmowy przy wskaźniku z modelu (Scaleway, UE); `pytanie: null`, gdy model nie odpowiedział. */
export async function pobierzPodpowiedz(
  token: string,
  procesId: number,
  wskaznikId: string,
): Promise<{ pytanie: string | null; dostawca?: string | null }> {
  const r = await fetch(`/api/procesy/${procesId}/rozmowa/podpowiedz`, {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify({ wskaznik_id: wskaznikId }),
  });
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc;
}

export const zapiszRozmowe = (token: string, procesId: number, zapis: ZapisRozmowy) =>
  zapiszOcene(token, procesId, "rozmowa", zapis);

export const zapiszDecyzje = (
  token: string,
  procesId: number,
  decyzje: Record<string, { punkty: number; uzasadnienie: string | null } | null>,
) => zapiszOcene(token, procesId, "decyzje", { decyzje });

/* Krok 6: wynik i terminy oceny okresowej (#32, kontrakt w issue #32). */

export interface SladReguly {
  regula: { id: string; zrodlo: SourceRef };
  opis: string;
}

export interface Termin {
  data: string;
  slad: SladReguly[];
}

export interface ZmianaTerminu {
  nowy_termin: string;
  data_zawiadomienia: string;
  przyczyna:
    | "zmiana_oceniajacego"
    | "przewidywana_nieobecnosc_ocenianego"
    | "przewidywana_nieobecnosc_oceniajacego"
    | "wniosek_ocenianego";
}

export interface DaneWyniku {
  data_ustalenia_kryteriow: string | null;
  data_zapoznania_z_kryteriami: string | null;
  data_sporzadzenia_oceny: string | null;
  data_zapoznania_z_ocena: string | null;
  data_zapoznania_z_poprzednia_ocena: string | null;
  zmiana_stanowiska: { data: string; istotna_zmiana_obowiazkow: boolean } | null;
  zmiana_terminu: ZmianaTerminu | null;
  uzasadnienie: string | null;
  poprzednia_ocena_poziom: string | null;
  dolacz_wniosek_o_stopien: boolean;
}

export interface WynikOkresowy {
  proces_id: number;
  arkusz: "B" | "C";
  zapisany: boolean;
  wersja_regul: string;
  oceny_czastkowe: { kompetencja_id: string; nazwa: string; rodzaj: "OBOWIAZKOWE" | "DODATKOWE"; punkty: number }[];
  obliczenie: {
    srednia: string;
    poziom: string;
    wynik: "pozytywna" | "negatywna";
    regula_rozstrzygajaca: { id: string; zrodlo: SourceRef };
    slad: SladReguly[];
  };
  uzasadnienie_wymagane: boolean;
  podstawa_uzasadnienia: SourceRef | null;
  dane: DaneWyniku;
  terminy: {
    termin_kryteriow: Termin | null;
    termin_bazowy: Termin | null;
    termin_sporzadzenia_oceny: Termin | null;
    termin_sprzeciwu: Termin | null;
    ponowne_kryteria: Termin | null;
    okno_zmiany_stanowiska: Termin | null;
    zachowaj_kryteria: boolean;
    slad: SladReguly[];
    braki: string[];
  };
  poprzednia_ocena: { data: string; wynik: "pozytywna" | "negatywna"; poziom: string | null } | null;
  czesc_iii: { dostepna: boolean; dolaczana: boolean; adnotacja: SourceRef };
  zawiadomienie_dostepne: boolean;
}

export const pobierzWynik = (token: string, procesId: number) =>
  fetch(`/api/procesy/${procesId}/wynik-okresowy`, { headers: autoryzacja(token) }).then(async (r) => {
    if (!r.ok) throw new BladApi(r.status, (await r.json().catch(() => null))?.detail);
    return (await r.json()) as WynikOkresowy;
  });

export async function zapiszWynik(token: string, procesId: number, dane: DaneWyniku): Promise<WynikOkresowy> {
  const r = await fetch(`/api/procesy/${procesId}/wynik-okresowy`, {
    method: "PUT",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify(dane),
  });
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as WynikOkresowy;
}

/** PDF wymaga nagłówka z tokenem, więc pobieramy go jako plik zamiast zwykłego linku. */
export async function pobierzZawiadomienie(token: string, procesId: number): Promise<Blob> {
  const r = await fetch(`/api/procesy/${procesId}/wynik-okresowy/zawiadomienie.pdf`, { headers: autoryzacja(token) });
  if (!r.ok) throw new BladApi(r.status, (await r.json().catch(() => null))?.detail);
  return r.blob();
}

/* Krok 6: plan rozmowy oceniającej (#35, kontrakt w issue #35). Niczego nie zapisuje. */

export interface PytanieRozmowy {
  id: string;
  tresc: string;
  uzasadnienie: string;
  powiazanie: {
    typ: "wskaznik" | "przyklad" | "zadanie_osp" | "przepis";
    kompetencja: string | null;
    wskaznik: string | null;
    wskaznik_id?: string | null;
    zadanie_osp: number | null;
  };
  adnotacje: SourceRef[];
}

export interface PlanRozmowy {
  proces_id: number;
  sciezka: Sciezka;
  wersja: string;
  status: string;
  oznaczenie: string;
  zakres: { id: string; punkt: string; adnotacje: SourceRef[] }[];
  pytania: PytanieRozmowy[];
  argumenty: {
    kompetencja: string;
    wskaznik_id: string;
    wskaznik: string;
    poziom: number | null;
    etykieta: string | null;
    zachowanie: string | null;
    zachowanie_zrodlo: SourceRef | null;
    przyklad: string | null;
    rezultat: string | null;
    uwaga: string | null;
  }[];
  informacja_zwrotna: { mocne_strony: string[]; obszary_rozwoju: string[] };
  kwestie: { id: string; tresc: string; adnotacje: SourceRef[] }[];
  tryb: string;
}

export interface DaneRozmowy {
  cele?: string[];
  sprawozdanie_zlozone_w_terminie?: boolean | null;
  egzamin_obowiazkowy?: boolean | null;
  fragment_sprawozdania?: string | null;
}

export async function przygotujRozmowe(token: string, procesId: number, dane: DaneRozmowy): Promise<PlanRozmowy> {
  const r = await fetch(`/api/procesy/${procesId}/rozmowa`, {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify(dane),
  });
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as PlanRozmowy;
}

export interface OdpowiedzCzatuRozmowy extends OdpowiedzAsystenta {
  oznaczenie_sugestii: string;
  /** Przygotowanie do rozmowy (zgłoszenie 178): sprawy do omówienia i argumenty z danych tej oceny. */
  kwestie?: string[];
  argumenty?: string[];
}

export async function pytajWczacieRozmowy(
  token: string,
  procesId: number,
  pytanie: string,
): Promise<OdpowiedzCzatuRozmowy> {
  const r = await fetch(`/api/procesy/${procesId}/rozmowa/czat`, {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify({ pytanie }),
  });
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as OdpowiedzCzatuRozmowy;
}

/* Krok 7: arkusz oceny okresowej B/C, PDF i mock EZD (#33, kontrakt w issue #33). */

export interface PoleArkusza {
  id: string;
  etykieta: string;
  rodzaj: string;
  warianty: (string | number)[];
  przypisy: number[];
  wartosc: string | null;
  widoczne: boolean;
  edytowalne: boolean;
  wymagane: boolean;
}

export interface BrakArkusza {
  id: string;
  etykieta: string;
  komunikat: string;
}

export interface RejestracjaEzd {
  numer_sprawy: string;
  zarejestrowano: string;
  sha256_pdf: string;
  mock: boolean;
}

export interface ArkuszOkresowy {
  proces_id: number;
  arkusz: "B" | "C";
  zrodlo: { sciezka: string; zalacznik: number; sha256: string };
  wersja_wzoru: string;
  sekcje: { tytul: string; widoczna: boolean; przypisy: number[]; pola: PoleArkusza[] }[];
  przypisy: Record<string, string>;
  braki: BrakArkusza[];
  pdf_dostepny: boolean;
  zatwierdzony: boolean;
  komunikat_podpis: string;
  rejestracja_ezd: RejestracjaEzd | null;
}

const sciezkaArkusza = (procesId: number) => `/api/procesy/${procesId}/arkusz-okresowy`;

async function odpowiedz<T>(r: Response): Promise<T> {
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as T;
}

export const pobierzArkusz = (token: string, procesId: number) =>
  fetch(sciezkaArkusza(procesId), { headers: autoryzacja(token) }).then((r) => odpowiedz<ArkuszOkresowy>(r));

export const zapiszArkusz = (token: string, procesId: number, pola: Record<string, string | null>, zatwierdz: boolean) =>
  fetch(sciezkaArkusza(procesId), {
    method: "PUT",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify({ pola, zatwierdz }),
  }).then((r) => odpowiedz<ArkuszOkresowy>(r));

export async function pobierzArkuszPdf(token: string, procesId: number): Promise<Blob> {
  const r = await fetch(`${sciezkaArkusza(procesId)}/pdf`, { headers: autoryzacja(token) });
  if (!r.ok) throw new BladApi(r.status, (await r.json().catch(() => null))?.detail);
  return r.blob();
}

/** Zakończenie oceny po zapoznaniu ocenianego z oceną (§ 12 ust. 1): status ZAKONCZONY, ocena trafia do kartoteki. */
export interface ZakonczenieOceny {
  proces_id: number;
  data_sporzadzenia_oceny: string;
  data_zapoznania_z_ocena: string;
  wynik: "pozytywna" | "negatywna";
  srednia: string;
}

export const zakonczOcene = (token: string, procesId: number, dataZapoznania: string) =>
  fetch(`${sciezkaArkusza(procesId)}/zakoncz`, {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify({ data_zapoznania_z_ocena: dataZapoznania }),
  }).then((r) => odpowiedz<ZakonczenieOceny>(r));

/** Sama część I arkusza do podpisu po rozmowie na początku okresu (rozp. 2016 § 5 ust. 3, § 6).
 *  409 przed zapisem kroku 2, 422 gdy nie da się ustalić terminu oceny. */
export async function pobierzCzescIPdf(token: string, procesId: number): Promise<Blob> {
  const r = await fetch(`${sciezkaArkusza(procesId)}/czesc-i/pdf`, { headers: autoryzacja(token) });
  if (!r.ok) throw new BladApi(r.status, (await r.json().catch(() => null))?.detail);
  return r.blob();
}

export const zarejestrujEzd = (token: string, procesId: number) =>
  fetch(`${sciezkaArkusza(procesId)}/ezd`, { method: "POST", headers: autoryzacja(token) }).then((r) =>
    odpowiedz<RejestracjaEzd>(r),
  );

/** Etap cyklu oceny osoby (#23): następna czynność i termin liczy backend z reguł obu ścieżek. */
export interface EtapOsoby {
  osoba_id: string;
  sciezka: Sciezka | null;
  etap: "kryteria" | "okres" | "ocena" | "brak_danych";
  czynnosc: string;
  termin: { nazwa: string; data: string; adnotacje: SourceRef[] } | null;
  dni_do_terminu: number | null;
  po_terminie: boolean;
  proces_id: number | null;
  kryteria_ustalone: string | null;
  braki: string[];
}

/** Mapa kompetencji zespołu (#33): punkty ocen cząstkowych; tylko z uprawnieniem do treści ocen (nie HR). */
export interface MapaKompetencji {
  skala: number[];
  poziom_oczekiwan: number;
  kryteria: { kompetencja_id: string; nazwa: string }[];
  osoby: {
    osoba_id: string;
    zrodlo: "biezaca_ocena" | "ostatnia_ocena";
    data: string | null;
    punkty: Record<string, number>;
    rozbieznosci: number | null;
  }[];
}

export const pobierzMapeKompetencji = (token: string) =>
  fetch("/api/zespol/kompetencje", { headers: autoryzacja(token) }).then((r) => json<MapaKompetencji>(r));

/** Demo (#186): kasuje dane oceny osoby demo, ocena zaczyna się od pierwszego etapu. */
export const zacznijOdPoczatku = (token: string, osobaId: string) =>
  fetch(`/api/demo/pracownicy/${osobaId}/od-poczatku`, { method: "POST", headers: autoryzacja(token) }).then((r) =>
    json<{ osoba_id: string; sciezka: string; usuniete_procesy: number }>(r),
  );

export const pobierzCykl = (token: string) =>
  fetch("/api/cykl", { headers: autoryzacja(token) }).then((r) => json<EtapOsoby[]>(r));

/* Panel HR: procesy, zagrożone terminy, przypomnienia (#38, kontrakt w issue #38). Bez treści ocen i notatek. */

export interface TerminHr {
  nazwa: string;
  data: string;
  adnotacje: SourceRef[];
}

export interface ProcesHr {
  proces_id: number;
  osoba_id: string;
  osoba: string;
  stanowisko: string;
  przelozony_id: string;
  sciezka: Sciezka;
  arkusz: "B" | "C" | "PIERWSZA";
  krok: number;
  status: string;
  najblizszy_termin: TerminHr | null;
  dni_do_terminu: number | null;
  zagrozony: boolean;
  komunikat: string | null;
}

export interface PropozycjaPrzypomnienia {
  proces_id: number;
  adresat: string;
  tresc: string;
  termin: TerminHr;
}

export interface Przypomnienie {
  id: number;
  proces_id: number;
  adresat: string;
  tresc: string;
  nadawca: string;
  wyslano: string;
}

export const pobierzProcesyHr = (token: string, zagrozone: boolean) =>
  fetch(`/api/hr/procesy?zagrozone=${zagrozone}`, { headers: autoryzacja(token) }).then((r) => odpowiedz<ProcesHr[]>(r));

export const pobierzPropozycjePrzypomnien = (token: string) =>
  fetch("/api/hr/przypomnienia/propozycje", { headers: autoryzacja(token) }).then((r) => odpowiedz<PropozycjaPrzypomnienia[]>(r));

export const pobierzSkrzynke = (token: string) =>
  fetch("/api/hr/skrzynka", { headers: autoryzacja(token) }).then((r) => odpowiedz<Przypomnienie[]>(r));

export const wyslijPrzypomnienie = (token: string, dane: { proces_id: number; adresat: string; tresc: string }) =>
  fetch("/api/hr/przypomnienia", {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify(dane),
  }).then((r) => odpowiedz<Przypomnienie>(r));

/* Krok 8: wnioski rozwojowe (#36, kontrakt w PR #76). Asystent niczego nie wpisuje. */

export interface PropozycjaRozwoju {
  typ: "OBSZAR_ROZWOJOWY" | "MOCNA_STRONA";
  kompetencja: string;
  wskaznik: string;
  wskaznik_id: string | null;
  poziom: number | null;
  przyklady: string[];
  formy: { id: string; nazwa: string; adnotacje: SourceRef[] }[];
  regula: string;
  uwagi: string[];
}

export interface WnioskiProcesu {
  proces_id: number;
  sciezka: Sciezka;
  wynik_oceny: "pozytywna" | "negatywna" | null;
  propozycje: {
    wersja_metodyki: string;
    dostepne: boolean;
    komunikat: string | null;
    propozycje: PropozycjaRozwoju[];
    pominiete: { kompetencja: string; wskaznik: string; powod: string }[];
    struktura_wnioskow: string[];
    tresc_wnioskow: string | null;
    reguly: { id: string; opis: string; adnotacje: SourceRef[] }[];
    status: string;
  };
  pole_arkusza: string | null;
  gdzie_wpisac: string;
  wnioski_w_arkuszu: string | null;
}

export const pobierzWnioski = (token: string, procesId: number) =>
  fetch(`/api/procesy/${procesId}/rozwoj`, { headers: autoryzacja(token) }).then((r) => odpowiedz<WnioskiProcesu>(r));

/** Cele rozwojowe (#10, #40): należą do pracownika; akceptację daje przełożony. */
export type StatusCelu = "propozycja" | "zatwierdzony" | "w_realizacji" | "osiągnięty" | "porzucony" | "odrzucony";

export interface TrescCelu {
  nazwa: string;
  opis?: string;
  wskaznik_id?: string | null;
  miernik: string;
  termin: string;
}

export interface Cel extends TrescCelu {
  id: number;
  osoba_id: string;
  opis: string;
  status: StatusCelu;
  komentarz: string | null;
  zgloszono_osiagniecie: boolean;
  autor: string;
  utworzono: string;
  zmieniono: string;
}

export interface WpisHistoriiCelu {
  czas: string;
  autor: string;
  "różnica"?: Record<string, { przed: unknown; po: unknown }>;
  roznica?: Record<string, { przed: unknown; po: unknown }>;
}

export interface PodpowiedzCelu {
  nazwa: string;
  opis: string;
  wskaznik_id: string | null;
  wskaznik: string | null;
  kompetencja: string | null;
  miernik: string;
  termin: string | null;
  formy: string[];
  oznaczenie: string;
}

async function wyslijCele<T>(token: string, url: string, method = "GET", body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: { ...autoryzacja(token), ...(body === undefined ? {} : { "content-type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const tresc = await r.json().catch(() => null);
  if (!r.ok) throw new BladApi(r.status, tresc?.detail);
  return tresc as T;
}

export const celeApi = {
  lista: (t: string, osoba: string) =>
    wyslijCele<{ osoba_id: string; pracownik_moze_edytowac: boolean; cele: Cel[] }>(t, `/api/pracownicy/${osoba}/cele`),
  historia: (t: string, id: number) => wyslijCele<WpisHistoriiCelu[]>(t, `/api/cele/${id}/historia`),
  podpowiedzi: (t: string, osoba: string) =>
    wyslijCele<{ proces_id: number | null; komunikat: string | null; podpowiedzi: PodpowiedzCelu[] }>(
      t,
      `/api/pracownicy/${osoba}/cele/podpowiedzi`,
    ),
  dodaj: (t: string, osoba: string, c: TrescCelu) => wyslijCele<Cel>(t, `/api/pracownicy/${osoba}/cele`, "POST", c),
  zmien: (t: string, id: number, c: TrescCelu) => wyslijCele<Cel>(t, `/api/cele/${id}`, "PUT", c),
  zatwierdz: (t: string, id: number) => wyslijCele<Cel>(t, `/api/cele/${id}/zatwierdz`, "POST"),
  odrzuc: (t: string, id: number, komentarz: string) => wyslijCele<Cel>(t, `/api/cele/${id}/odrzuc`, "POST", { komentarz }),
  status: (t: string, id: number, status: "w_realizacji" | "osiągnięty" | "porzucony") =>
    wyslijCele<Cel>(t, `/api/cele/${id}/status`, "POST", { status }),
};

/* Pierwsza ocena: terminy, sprawozdanie, egzamin, wynik § 10 i arkusz (#34, kontrakt w issue #34). */

export interface SprawozdaniePierwszej {
  zadania: string;
  problemy_i_rozwiazania: string;
  nowe_umiejetnosci_i_wiedza: string;
  propozycje_usprawnien: string;
}

export type PrzeslankaEgzaminu = "ksap_bez_wniosku" | "zastepstwo" | "wyzsze_stanowisko";

export interface EgzaminPierwszej {
  wynik: "tak" | "nie" | "nie_dotyczy";
  przeslanka: PrzeslankaEgzaminu | null;
}

export interface PrzedluzeniePierwszej {
  nowy_termin: string;
  data_zawiadomienia: string;
  przyczyna: "usprawiedliwiona_nieobecnosc" | "obowiazki_poza_miejscem_pracy" | "przedluzenie_umowy";
  okres_od: string | null;
  okres_do: string | null;
  nowy_termin_od: string | null;
}

export interface DanePierwszej {
  data_ustalenia_oceny_zastepstwa: string | null;
  data_konca_zatrudnienia: string | null;
  data_rozmowy_wstepnej: string | null;
  termin_sprawozdania_od: string | null;
  wyznaczony_termin_sprawozdania: string | null;
  przedluzenie: PrzedluzeniePierwszej | null;
  data_zlozenia_sprawozdania: string | null;
  sprawozdanie_niezlozone: boolean;
  sprawozdanie_okres_od: string | null;
  sprawozdanie_okres_do: string | null;
  data_rozmowy_oceniajacej: string | null;
  data_sporzadzenia_oceny: string | null;
  data_zapoznania_z_ocena: string | null;
  sprawozdanie: SprawozdaniePierwszej | null;
  egzamin: EgzaminPierwszej | null;
  uzasadnienie: string | null;
  wnioski_rozwojowe: string | null;
  pola: Record<string, string | null>;
}

export interface StanPierwszejOceny {
  proces_id: number;
  wersja_regul: string;
  dane: DanePierwszej;
  terminy: Record<string, Termin | string | boolean | null | string[] | SladReguly[]> & {
    slad: SladReguly[];
    braki: string[];
    uwagi: string[];
  };
  egzamin: EgzaminPierwszej | null;
  przeslanki_egzaminu: Record<PrzeslankaEgzaminu, SourceRef>;
  obliczenie: WynikOkresowy["obliczenie"] | null;
  warunki: { id: string; opis: string; spelniony: boolean; zrodlo: SourceRef }[];
  uzasadnienie_wymagane: boolean;
  podstawa_uzasadnienia: SourceRef;
  wnioski_dostepne: boolean;
  podstawa_wnioskow: SourceRef;
  mapowanie: { wartosci: Record<string, number>; adnotacje: SourceRef[] };
  wersja_metodyki: string;
  zawiadomienie_dostepne: boolean;
  formularz: Omit<ArkuszOkresowy, "proces_id" | "arkusz" | "wersja_wzoru" | "rejestracja_ezd">;
}

const sciezkaPierwszej = (procesId: number) => `/api/procesy/${procesId}/pierwsza-ocena`;

export const pobierzPierwsza = (token: string, procesId: number) =>
  fetch(sciezkaPierwszej(procesId), { headers: autoryzacja(token) }).then((r) => odpowiedz<StanPierwszejOceny>(r));

export const zapiszPierwsza = (token: string, procesId: number, dane: DanePierwszej, zatwierdz: boolean) =>
  fetch(sciezkaPierwszej(procesId), {
    method: "PUT",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify({ ...dane, zatwierdz }),
  }).then((r) => odpowiedz<StanPierwszejOceny>(r));

/** Zakończenie pierwszej oceny po zapoznaniu ocenianego z oceną (§ 11 ust. 1 rozp. 2015): status ZAKONCZONY. */
export const zakonczPierwsza = (token: string, procesId: number, dataZapoznania: string) =>
  fetch(`${sciezkaPierwszej(procesId)}/zakoncz`, {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify({ data_zapoznania_z_ocena: dataZapoznania }),
  }).then((r) => odpowiedz<StanPierwszejOceny>(r));

export async function pobierzPdfPierwszej(token: string, procesId: number, plik: "arkusz.pdf" | "zawiadomienie.pdf" | "rozmowa-wstepna.pdf"): Promise<Blob> {
  const r = await fetch(`${sciezkaPierwszej(procesId)}/${plik}`, { headers: autoryzacja(token) });
  if (!r.ok) throw new BladApi(r.status, (await r.json().catch(() => null))?.detail);
  return r.blob();
}

/* Wersje metodyki sugestii i mapowania 5→3 z zatwierdzaniem (#39, kontrakt w PR #67). */

export interface WersjaMetodyki {
  id: string;
  numer: number;
  status: "PROJEKT" | "ZATWIERDZONA" | "ZASTĄPIONA";
  minimalny_udzial_ocenionych: number;
  mapowanie_pierwsza: Record<string, number>;
  zmiana: string;
  utworzyl: string;
  utworzono: string;
  zatwierdzil: string | null;
  data_zatwierdzenia: string | null;
}

export const pobierzMetodyke = (token: string) =>
  fetch("/api/metodyka", { headers: autoryzacja(token) }).then((r) => odpowiedz<{ aktywna: string; wersje: WersjaMetodyki[] }>(r));

export const utworzWersjeMetodyki = (
  token: string,
  dane: { minimalny_udzial_ocenionych: number; mapowanie_pierwsza: Record<string, number>; zmiana: string },
) =>
  fetch("/api/metodyka", {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify(dane),
  }).then((r) => odpowiedz<WersjaMetodyki>(r));

export const zatwierdzMetodyke = (token: string, id: string, dane: { osoba: string | null; dzien: string | null }) =>
  fetch(`/api/metodyka/${encodeURIComponent(id)}/zatwierdz`, {
    method: "POST",
    headers: { "content-type": "application/json", ...autoryzacja(token) },
    body: JSON.stringify(dane),
  }).then((r) => odpowiedz<WersjaMetodyki>(r));

/* Rejestr operacji (Karol 22.11): kto, co, komu i z jakim skutkiem; tylko HR (rejestr.czytaj). */
export type WynikOperacji = "ok" | "odmowa" | "blad";

export interface WpisRejestru {
  id: number;
  czas: string;
  request_id: string | null;
  aktor_login: string | null;
  aktor_rola: string | null;
  aktor_osoba: string | null;
  akcja: string;
  etykieta: string | null;
  metoda: string | null;
  trasa: string | null;
  obiekt: string | null;
  oceniany_osoba: string | null;
  wynik: WynikOperacji;
  status: number | null;
  czas_ms: number | null;
  szczegoly: Record<string, unknown>;
}

export interface StronaRejestru {
  wpisy: WpisRejestru[];
  razem: number;
  strona: number;
  na_stronie: number;
}

export interface FiltryRejestru {
  od?: string | null;
  do?: string | null;
  uzytkownik?: string | null;
  wynik?: WynikOperacji | null;
  osoba?: string | null;
}

const zapytanieRejestru = (f: FiltryRejestru, dodatkowe: Record<string, string> = {}) =>
  new URLSearchParams(
    Object.entries({ ...f, ...dodatkowe }).filter((p): p is [string, string] => typeof p[1] === "string" && p[1] !== ""),
  ).toString();

export const pobierzRejestr = (token: string, filtry: FiltryRejestru, strona: number) =>
  fetch(`/api/rejestr?${zapytanieRejestru(filtry, { strona: String(strona), na_stronie: "50" })}`, {
    headers: autoryzacja(token),
  }).then((r) => odpowiedz<StronaRejestru>(r));

export async function pobierzRejestrCsv(token: string, filtry: FiltryRejestru): Promise<Blob> {
  const r = await fetch(`/api/rejestr.csv?${zapytanieRejestru(filtry)}`, { headers: autoryzacja(token) });
  if (!r.ok) throw new BladApi(r.status, (await r.json().catch(() => null))?.detail);
  return r.blob();
}
