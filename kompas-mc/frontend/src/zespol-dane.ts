import type { EtapOsoby, Pracownik, ProcesOceny, Sciezka, TerminProcesu } from "./api";

/** Wspólne obliczenia pulpitu, zakładki Zespół i karty pracownika: wszystko z danych API, bez własnych reguł. */

export const data = (iso: string) => iso.slice(0, 10).split("-").reverse().join(".");

/** Komórka z QNT ma postać „Departament … / Wydział …”. */
export function podzial(komorka: string): { departament: string; wydzial: string } {
  const [departament, ...reszta] = komorka.split(" / ");
  return { departament, wydzial: reszta.join(" / ") || departament };
}

/** Pełne lata pracy od daty zatrudnienia do dziś. */
export function lataStazu(od: string, dzis = new Date()): number {
  const d = new Date(od);
  let lata = dzis.getFullYear() - d.getFullYear();
  if (dzis.getMonth() < d.getMonth() || (dzis.getMonth() === d.getMonth() && dzis.getDate() < d.getDate())) lata--;
  return Math.max(0, lata);
}

export function odmiana(n: number, jeden: string, kilka: string, wiele: string): string {
  if (n === 1) return jeden;
  const d = n % 10;
  const s = n % 100;
  return d >= 2 && d <= 4 && (s < 12 || s > 14) ? kilka : wiele;
}

export const osoby = (n: number) => `${n} ${odmiana(n, "osoba", "osoby", "osób")}`;
export const dni = (n: number) => `${n} ${odmiana(n, "dzień", "dni", "dni")}`;
export const lat = (n: number) => `${n} ${odmiana(n, "rok", "lata", "lat")}`;
export const stazTekst = (n: number) => (n < 1 ? "poniżej roku stażu" : `${lat(n)} stażu`);

export function kiedy(dniDo: number): string {
  if (dniDo < 0) return `${dni(-dniDo)} po terminie`;
  if (dniDo === 0) return "dziś";
  return `za ${dni(dniDo)}`;
}

export const NAZWA_SCIEZKI: Record<Sciezka, string> = { pierwsza: "pierwsza ocena", okresowa: "ocena okresowa" };

/** Stan oceny osoby: proces w toku, propozycja ścieżki z analizy kroku 1 albo brak. */
export interface Sprawa {
  osoba: Pracownik;
  proces: ProcesOceny | null;
  proponowana: Sciezka | null;
  termin: TerminProcesu | null;
  /** Etap cyklu i następna czynność z /api/cykl (#23); null, gdy API go nie zwróciło. */
  cykl: EtapOsoby | null;
}

/** Czynność i termin po ludzku: „Rozmowa oceniająca · do 02.12.2026”. */
export function nastepnyKrok(s: Sprawa): string {
  const c = s.cykl;
  if (c) return c.termin ? `${c.czynnosc} · do ${data(c.termin.data)}` : c.czynnosc;
  if (s.proces) return `Ocena w toku · krok ${s.proces.krok} z 8`;
  if (s.proponowana === "pierwsza") return "Rozpocznij pierwszą ocenę";
  if (s.proponowana === "okresowa") return "Rozpocznij ocenę okresową";
  return "Ustal ścieżkę oceny";
}

/** Do zrobienia teraz: ustalenie kryteriów, ocena albo brak danych; „okres” to czas między nimi. */
export const doZrobienia = ({ cykl }: Pick<Sprawa, "cykl">) => !!cykl && cykl.etap !== "okres";
export const poTerminie = (s: Sprawa) => !!s.cykl?.po_terminie;
/** Termin w ciągu 14 dni (bez już przekroczonych). */
export const wkrotce = (s: Sprawa) =>
  !!s.cykl && !s.cykl.po_terminie && s.cykl.dni_do_terminu !== null && s.cykl.dni_do_terminu <= 14;

/** Grupy według departamentu i wydziału, w kolejności alfabetycznej. */
export function wedlugKomorek<T>(lista: T[], komorka: (x: T) => string) {
  const mapa = new Map<string, Map<string, T[]>>();
  for (const x of lista) {
    const { departament, wydzial } = podzial(komorka(x));
    const dep = mapa.get(departament) ?? new Map<string, T[]>();
    dep.set(wydzial, [...(dep.get(wydzial) ?? []), x]);
    mapa.set(departament, dep);
  }
  return [...mapa.entries()]
    .sort(([a], [b]) => a.localeCompare(b, "pl"))
    .map(([departament, wydzialy]) => ({
      departament,
      wydzialy: [...wydzialy.entries()].sort(([a], [b]) => a.localeCompare(b, "pl")).map(([wydzial, ludzie]) => ({ wydzial, ludzie })),
    }));
}

/** Filtr listy Pracownicy, ustawiany kliknięciem liczby albo komórki w Zespole (i na pulpicie). */
export interface FiltrPracownikow {
  /** Pełna nazwa departamentu albo „Departament … / Wydział …”: prefiks pola komorka z QNT. */
  komorka?: string;
  /** Etap cyklu z /api/cykl. */
  etap?: EtapOsoby["etap"];
  /** Termin: przekroczony albo w ciągu 14 dni. */
  termin?: "po_terminie" | "wkrotce";
  stan?: "w_toku" | "do_rozpoczecia" | "zagrozony" | "bez_sciezki";
  sciezka?: Sciezka;
  ocena?: "pozytywna" | "negatywna" | "brak";
  /** Osoby wymagające działania, jak licznik „do zrobienia” na pulpicie (zgłoszenie 187). */
  doZrobienia?: boolean;
}

export type StanSprawy = NonNullable<FiltrPracownikow["stan"]>;

export function stanSprawy(s: Sprawa): StanSprawy {
  if (s.proces && s.termin?.zagrozony) return "zagrozony";
  if (s.proces) return "w_toku";
  if (s.proponowana) return "do_rozpoczecia";
  return "bez_sciezki";
}

export function pasuje(s: Sprawa, f: FiltrPracownikow): boolean {
  if (f.komorka && !(s.osoba.komorka === f.komorka || s.osoba.komorka.startsWith(`${f.komorka} / `))) return false;
  if (f.stan) {
    const st = stanSprawy(s);
    // „W toku” obejmuje też zagrożone: zagrożony proces nadal jest w toku.
    if (f.stan === "w_toku" ? !(st === "w_toku" || st === "zagrozony") : st !== f.stan) return false;
  }
  if (f.etap && s.cykl?.etap !== f.etap) return false;
  if (f.termin === "po_terminie" && !poTerminie(s)) return false;
  if (f.termin === "wkrotce" && !wkrotce(s)) return false;
  if (f.sciezka && (s.cykl?.sciezka ?? s.proponowana) !== f.sciezka) return false;
  if (f.ocena && (s.osoba.ostatnia_ocena_okresowa?.wynik ?? "brak") !== f.ocena) return false;
  if (f.doZrobienia && !doZrobienia(s)) return false;
  return true;
}

export const NAZWA_STANU: Record<StanSprawy, string> = {
  zagrozony: "termin w ciągu 7 dni",
  w_toku: "ocena w toku",
  do_rozpoczecia: "do rozpoczęcia",
  bez_sciezki: "ścieżka do ustalenia",
};

export const NAZWA_ETAPU: Record<EtapOsoby["etap"], string> = {
  kryteria: "ustalenie kryteriów",
  okres: "okres oceny",
  ocena: "ocena końcowa",
  brak_danych: "brak danych kadrowych",
};
