import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import type { EtapOsoby, Pracownik } from "./api";
import { Ikona } from "./Ikona";
import type { Sesja } from "./Konto";
import { Inicjaly } from "./Lista";
import { useSprawy } from "./Zespol";
import {
  data,
  dni,
  NAZWA_ETAPU,
  NAZWA_SCIEZKI,
  NAZWA_STANU,
  osoby,
  pasuje,
  podzial,
  type FiltrPracownikow,
  type Sprawa,
} from "./zespol-dane";
import "./widoki.css";
import "./tabela.css";

/**
 * Pracownicy jako tabela (#54, na 1000 osób): sortowanie nagłówkiem, grupowanie, wybór kolumn, wyszukiwarka i filtry
 * z liczbą osób przy każdej opcji, stronicowanie po 50 wierszy. Filtry etapu, terminu, ścieżki i oceny zapisują się
 * w tym samym filtrze co kliknięcie w Zespole; komórka z Zespołu zostaje znacznikiem do zdjęcia. Wiersz otwiera kartę.
 */
type Kolumna = "osoba" | "stanowisko" | "departament" | "wydzial" | "sciezka" | "czynnosc" | "termin" | "ocena";
export type Grupowanie = "brak" | "departament" | "wydzial" | "etap";
type KluczFiltra = "etap" | "termin" | "sciezka" | "ocena";
interface Sortowanie {
  kolumna: Kolumna;
  malejaco: boolean;
}
interface Grupa {
  klucz: string;
  nazwa: string;
  opis?: string;
  ludzie: Sprawa[];
}
type Pozycja = { grupa: Grupa; ciag?: boolean } | { s: Sprawa };

const NA_STRONE = 50;
const KLUCZ_KOLUMN = "kompas-mc-pracownicy-ukryte-kolumny";
const porownaj = new Intl.Collator("pl").compare;
const wielka = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
const kto = (s: Sprawa) => `${s.osoba.nazwisko} ${s.osoba.imie}`;
const sciezka = (s: Sprawa) => s.cykl?.sciezka ?? s.proponowana;
/** Dni do terminu jak w kolejności z useSprawy: z cyklu, bez etapu z procesu w toku. */
const dniDoTerminu = (s: Sprawa) => s.cykl?.dni_do_terminu ?? s.termin?.dni_do_terminu ?? null;
const dataTerminu = (s: Sprawa) => s.cykl?.termin?.data ?? s.termin?.najblizszy_termin?.data ?? null;

/** Kolejność etapów: najpierw to, co trzeba zrobić teraz, okres oceny na końcu. */
const ETAPY: EtapOsoby["etap"][] = ["kryteria", "ocena", "brak_danych", "okres"];

/** Długa nazwa komórki: najwyżej dwie linie w wierszu, pełna w podpowiedzi, w nagłówku grupy i na karcie. */
const NazwaKomorki = ({ nazwa }: { nazwa: string }) => (
  <span className="nazwa-komorki" title={nazwa}>
    {nazwa}
  </span>
);

const KOLUMNY: { id: Kolumna; nazwa: string; klucz: (s: Sprawa) => string | number | null; komorka: (s: Sprawa) => ReactNode }[] = [
  {
    id: "osoba",
    nazwa: "Osoba",
    klucz: kto,
    komorka: (s) => (
      <span className="osoba-w-tabeli">
        <Inicjaly imie={s.osoba.imie} nazwisko={s.osoba.nazwisko} />
        <span>
          {s.osoba.imie} <span className="bez-lamania">{s.osoba.nazwisko}</span>
        </span>
      </span>
    ),
  },
  { id: "stanowisko", nazwa: "Stanowisko", klucz: (s) => s.osoba.stanowisko, komorka: (s) => s.osoba.stanowisko },
  {
    id: "departament",
    nazwa: "Departament",
    klucz: (s) => podzial(s.osoba.komorka).departament,
    komorka: (s) => <NazwaKomorki nazwa={podzial(s.osoba.komorka).departament} />,
  },
  {
    id: "wydzial",
    nazwa: "Wydział",
    klucz: (s) => podzial(s.osoba.komorka).wydzial,
    komorka: (s) => <NazwaKomorki nazwa={podzial(s.osoba.komorka).wydzial} />,
  },
  {
    id: "sciezka",
    nazwa: "Ścieżka",
    klucz: (s) => (sciezka(s) ? NAZWA_SCIEZKI[sciezka(s)!] : null),
    komorka: (s) => (sciezka(s) ? NAZWA_SCIEZKI[sciezka(s)!] : <span className="meta">do ustalenia</span>),
  },
  {
    id: "czynnosc",
    nazwa: "Czynność",
    klucz: (s) => s.cykl?.czynnosc ?? null,
    komorka: (s) =>
      s.cykl ? (
        <span className="komorka-pionowa">
          <span className="czynnosc-wiersza">{s.cykl.czynnosc}</span>
          <span className="meta">{NAZWA_ETAPU[s.cykl.etap]}</span>
        </span>
      ) : (
        <span className="meta">bez ustalonego etapu</span>
      ),
  },
  {
    id: "termin",
    nazwa: "Termin",
    klucz: dniDoTerminu,
    komorka: (s) => {
      const d = dataTerminu(s);
      return d ? (
        <span className="komorka-pionowa">
          {data(d)}
          <PlakietkaTerminu s={s} />
        </span>
      ) : (
        <span className="meta">bez terminu</span>
      );
    },
  },
  {
    id: "ocena",
    nazwa: "Ostatnia ocena",
    klucz: (s) => s.osoba.ostatnia_ocena_okresowa?.data ?? null,
    komorka: (s) => {
      const o = s.osoba.ostatnia_ocena_okresowa;
      return o ? (
        <span className="komorka-pionowa">
          <span className={`status ${o.wynik}`}>{o.wynik}</span>
          <span className="meta">{data(o.data)}</span>
        </span>
      ) : (
        <span className="meta">bez oceny</span>
      );
    },
  },
];

const FILTRY: { klucz: KluczFiltra; nazwa: string; opcje: [string, string][] }[] = [
  { klucz: "etap", nazwa: "Etap", opcje: ETAPY.map((e) => [e, NAZWA_ETAPU[e]]) },
  {
    klucz: "termin",
    nazwa: "Termin",
    opcje: [
      ["po_terminie", "po terminie"],
      ["wkrotce", "w ciągu 14 dni"],
    ],
  },
  { klucz: "sciezka", nazwa: "Ścieżka", opcje: Object.entries(NAZWA_SCIEZKI) },
  {
    klucz: "ocena",
    nazwa: "Ostatnia ocena",
    opcje: [
      ["pozytywna", "pozytywna"],
      ["negatywna", "negatywna"],
      ["brak", "bez oceny"],
    ],
  },
];

const NAZWA_GRUPOWANIA: Record<Grupowanie, string> = {
  brak: "bez grupowania",
  departament: "departament",
  wydzial: "wydział",
  etap: "etap",
};

/** Sortowanie stabilne; puste wartości (brak terminu, brak oceny) zawsze na końcu, remis po nazwisku. */
function posortuj(lista: Sprawa[], { kolumna, malejaco }: Sortowanie): Sprawa[] {
  const klucz = KOLUMNY.find((k) => k.id === kolumna)!.klucz;
  return lista
    .map((s) => [klucz(s), s] as const)
    .sort(([a, sa], [b, sb]) => {
      const roznica =
        a === null || b === null
          ? (a === null ? 1 : 0) - (b === null ? 1 : 0)
          : (malejaco ? -1 : 1) * (typeof a === "number" && typeof b === "number" ? a - b : porownaj(String(a), String(b)));
      return roznica || porownaj(kto(sa), kto(sb));
    })
    .map(([, s]) => s);
}

/** Grupy w kolejności alfabetycznej (etapy: najpierw do zrobienia); osoby w grupie zachowują kolejność sortowania. */
function pogrupuj(lista: Sprawa[], g: Grupowanie): Grupa[] {
  if (g === "brak") return [{ klucz: "", nazwa: "", ludzie: lista }];
  const mapa = new Map<string, Grupa>();
  for (const s of lista) {
    const { departament, wydzial } = podzial(s.osoba.komorka);
    const [klucz, nazwa, opis] =
      g === "departament"
        ? [departament, departament]
        : g === "wydzial"
          ? [s.osoba.komorka, wydzial, departament]
          : [s.cykl?.etap ?? "", s.cykl ? wielka(NAZWA_ETAPU[s.cykl.etap]) : "Bez ustalonego etapu"];
    const grupa = mapa.get(klucz) ?? { klucz, nazwa, opis, ludzie: [] };
    grupa.ludzie.push(s);
    mapa.set(klucz, grupa);
  }
  const miejsce = (x: Grupa) => {
    const i = ETAPY.indexOf(x.klucz as EtapOsoby["etap"]);
    return g === "etap" && i >= 0 ? i : ETAPY.length;
  };
  return [...mapa.values()].sort((a, b) => (g === "etap" ? miejsce(a) - miejsce(b) : 0) || porownaj(a.nazwa, b.nazwa));
}

/**
 * Strony po 50 wierszy osób. Nagłówek grupy idzie na stronę z jej pierwszym wierszem, a gdy grupa przechodzi
 * na kolejną stronę, powtarza się tam jako „ciąg dalszy”. Zwinięta grupa zajmuje tylko swój nagłówek.
 */
function stronicuj(grupy: Grupa[], zwiniete: Set<string>, zNaglowkami: boolean): Pozycja[][] {
  const strony: Pozycja[][] = [[]];
  let wiersze = 0;
  const nowa = (start: Pozycja[]) => {
    strony.push(start);
    wiersze = 0;
  };
  for (const g of grupy) {
    const zwinieta = zwiniete.has(g.klucz);
    if (zNaglowkami && !zwinieta && wiersze === NA_STRONE) nowa([]);
    if (zNaglowkami) strony[strony.length - 1].push({ grupa: g });
    if (zwinieta) continue;
    for (const s of g.ludzie) {
      if (wiersze === NA_STRONE) nowa(zNaglowkami ? [{ grupa: g, ciag: true }] : []);
      strony[strony.length - 1].push({ s });
      wiersze++;
    }
  }
  return strony;
}

function wczytajUkryte(): Kolumna[] {
  try {
    const zapis: unknown = JSON.parse(localStorage.getItem(KLUCZ_KOLUMN) ?? "[]");
    return Array.isArray(zapis) ? KOLUMNY.filter((k) => k.id !== "osoba" && zapis.includes(k.id)).map((k) => k.id) : [];
  } catch {
    return [];
  }
}

export function ListaPracownikow({
  sesja,
  filtr,
  onFiltr,
  onWybierz,
  onWyloguj,
  grupuj,
}: {
  sesja: Sesja;
  filtr: FiltrPracownikow;
  onFiltr: (f: FiltrPracownikow) => void;
  onWybierz: (p: Pracownik) => void;
  onWyloguj: () => void;
  /** Grupowanie na start (skrót „wydziały” z pulpitu, zgłoszenie 187); dalej zmienia je użytkownik. */
  grupuj?: Grupowanie;
}) {
  const { sprawy, blad } = useSprawy(sesja, onWyloguj);
  const oceniany = sesja.uzytkownik.rola === "oceniany";
  const [szukaj, setSzukaj] = useState("");
  const [sort, setSort] = useState<Sortowanie>({ kolumna: "termin", malejaco: false });
  const [grupowanie, setGrupowanie] = useState<Grupowanie>(grupuj ?? "brak");
  const [zwiniete, setZwiniete] = useState<Set<string>>(() => new Set());
  const [ukryte, setUkryte] = useState<Kolumna[]>(wczytajUkryte);
  const [strona, setStrona] = useState(0);
  const tabela = useRef<HTMLTableElement>(null);

  useEffect(() => localStorage.setItem(KLUCZ_KOLUMN, JSON.stringify(ukryte)), [ukryte]);
  useEffect(() => setStrona(0), [filtr, szukaj, sort, grupowanie]);

  // Wyszukiwarka zawęża bazę; liczba przy opcji filtra mówi, ile osób z tej bazy zostanie po jej wyborze.
  const znalezione = useMemo(() => {
    const q = szukaj.trim().toLowerCase();
    if (!q) return sprawy ?? [];
    return (sprawy ?? []).filter((s) =>
      `${s.osoba.imie} ${s.osoba.nazwisko} ${s.osoba.stanowisko} ${s.osoba.komorka}`.toLowerCase().includes(q),
    );
  }, [sprawy, szukaj]);
  const widoczne = useMemo(() => znalezione.filter((s) => pasuje(s, filtr)), [znalezione, filtr]);
  const strony = useMemo(
    () => stronicuj(pogrupuj(posortuj(widoczne, sort), grupowanie), zwiniete, grupowanie !== "brak"),
    [widoczne, sort, grupowanie, zwiniete],
  );
  const nr = Math.min(strona, strony.length - 1);
  const kolumny = KOLUMNY.filter((k) => !ukryte.includes(k.id));

  const liczba = (klucz: KluczFiltra, wartosc?: string) =>
    znalezione.filter((s) => pasuje(s, { ...filtr, [klucz]: wartosc } as FiltrPracownikow)).length;
  const zFiltrem = (zmiana: FiltrPracownikow) => onFiltr({ ...filtr, ...zmiana });
  const przelaczGrupe = (klucz: string) =>
    setZwiniete((z) => {
      const nowe = new Set(z);
      if (!nowe.delete(klucz)) nowe.add(klucz);
      return nowe;
    });
  const idzDo = (n: number) => {
    setStrona(n);
    tabela.current?.scrollIntoView({ block: "start" });
  };

  // Komórka i stan przychodzą tylko z Zespołu (nie ma ich w menu): znacznik do zdjęcia.
  const znaczniki: [keyof FiltrPracownikow, string][] = [];
  if (filtr.komorka) znaczniki.push(["komorka", podzial(filtr.komorka).wydzial]);
  if (filtr.stan) znaczniki.push(["stan", NAZWA_STANU[filtr.stan]]);
  if (filtr.doZrobienia) znaczniki.push(["doZrobienia", "do zrobienia"]);
  const cokolwiek = Object.values(filtr).some(Boolean) || szukaj.trim() !== "";
  const wyczysc = () => {
    setSzukaj("");
    onFiltr({});
  };

  return (
    <div className="widok">
      <div className="naglowek-widoku">
        <h1>{oceniany ? "Twoje dane" : "Pracownicy"}</h1>
        {sprawy && !oceniany && (
          <p className="meta licznik-osob" aria-live="polite">
            {widoczne.length} z {sprawy.length} {sprawy.length === 1 ? "osoby" : "osób"}
          </p>
        )}
      </div>

      {!oceniany && (
        <div className="listwa">
          <label className="pole-zapytania szukaj-pracownika">
            <Ikona nazwa="szukaj" />
            <input
              value={szukaj}
              onChange={(e) => setSzukaj(e.target.value)}
              placeholder="Szukaj po imieniu, nazwisku, stanowisku albo komórce…"
              aria-label="Szukaj pracownika"
              autoComplete="off"
            />
          </label>
          <div className="listwa-przyciski">
            {FILTRY.map((f) => {
              const wybrana = filtr[f.klucz];
              const nazwa = f.opcje.find(([w]) => w === wybrana)?.[1];
              return (
                <Rozwijane key={f.klucz} etykieta={nazwa ? `${f.nazwa}: ${nazwa}` : f.nazwa} aktywne={!!wybrana}>
                  {(zamknij) =>
                    [[undefined, "wszystkie"] as [string | undefined, string], ...f.opcje].map(([w, n]) => (
                      <button
                        key={n}
                        type="button"
                        className="opcja"
                        aria-pressed={wybrana === w}
                        onClick={() => {
                          zFiltrem({ [f.klucz]: w });
                          zamknij();
                        }}
                      >
                        <span>{wielka(n)}</span>
                        <span className="liczba-opcji">{liczba(f.klucz, w)}</span>
                      </button>
                    ))
                  }
                </Rozwijane>
              );
            })}
            <span className="listwa-odstep" />
            <Rozwijane
              etykieta={grupowanie === "brak" ? "Grupuj" : `Grupuj: ${NAZWA_GRUPOWANIA[grupowanie]}`}
              aktywne={grupowanie !== "brak"}
              doPrawej
            >
              {(zamknij) =>
                (Object.keys(NAZWA_GRUPOWANIA) as Grupowanie[]).map((g) => (
                  <button
                    key={g}
                    type="button"
                    className="opcja"
                    aria-pressed={grupowanie === g}
                    onClick={() => {
                      setGrupowanie(g);
                      zamknij();
                    }}
                  >
                    {wielka(NAZWA_GRUPOWANIA[g])}
                  </button>
                ))
              }
            </Rozwijane>
            <Rozwijane
              etykieta={ukryte.length ? `Kolumny: ${kolumny.length} z ${KOLUMNY.length}` : "Kolumny"}
              aktywne={ukryte.length > 0}
              doPrawej
            >
              {() =>
                KOLUMNY.map((k) => (
                  <label key={k.id} className="opcja">
                    <input
                      type="checkbox"
                      checked={!ukryte.includes(k.id)}
                      disabled={k.id === "osoba"}
                      onChange={() => setUkryte((u) => (u.includes(k.id) ? u.filter((x) => x !== k.id) : [...u, k.id]))}
                    />
                    {k.nazwa}
                  </label>
                ))
              }
            </Rozwijane>
          </div>
          {(znaczniki.length > 0 || cokolwiek) && (
            <div className="etykiety listwa-znaczniki">
              {znaczniki.map(([klucz, tekst]) => (
                <button
                  key={klucz}
                  type="button"
                  className="znacznik-filtra"
                  aria-label={`Usuń filtr: ${tekst}`}
                  onClick={() => zFiltrem({ [klucz]: undefined })}
                >
                  {tekst}
                  <Ikona nazwa="krzyz" rozmiar={16} />
                </button>
              ))}
              {cokolwiek && (
                <button type="button" className="link" onClick={wyczysc}>
                  Pokaż wszystkich
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {blad && <p className="blad">{blad}</p>}
      {!blad && !sprawy && (
        <div className="szkielet-tabeli" aria-busy="true" aria-label="Wczytuję">
          {Array.from({ length: 7 }, (_, i) => (
            <span key={i} />
          ))}
        </div>
      )}
      {sprawy && widoczne.length === 0 && (
        <div className="pusta-tabela">
          <p className="meta">Nikt nie pasuje do wyszukiwania i filtrów.</p>
          {cokolwiek && (
            <button type="button" className="jasny" onClick={wyczysc}>
              Pokaż wszystkich
            </button>
          )}
        </div>
      )}

      {widoczne.length > 0 && (
        <div className="tabela-przewijana">
          <table className="tabela-pracownikow" ref={tabela}>
            <thead>
              <tr>
                {kolumny.map((k) => {
                  const ta = sort.kolumna === k.id;
                  return (
                    <th
                      key={k.id}
                      scope="col"
                      className={`kol-${k.id}`}
                      aria-sort={ta ? (sort.malejaco ? "descending" : "ascending") : undefined}
                    >
                      <button
                        type="button"
                        className="sortuj"
                        onClick={() => setSort((s) => ({ kolumna: k.id, malejaco: s.kolumna === k.id && !s.malejaco }))}
                      >
                        {k.nazwa}
                        {ta && <Ikona nazwa="gora" rozmiar={16} />}
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {strony[nr].map((p) =>
                "grupa" in p ? (
                  <tr key={`grupa-${p.grupa.klucz}`} className="wiersz-grupy">
                    <th colSpan={kolumny.length}>
                      <button
                        type="button"
                        className="grupa"
                        aria-expanded={!zwiniete.has(p.grupa.klucz)}
                        onClick={() => przelaczGrupe(p.grupa.klucz)}
                      >
                        <Ikona nazwa="dalej" rozmiar={20} />
                        <span className="nazwa-grupy">
                          <strong>
                            {p.grupa.nazwa}
                            {p.ciag && " (ciąg dalszy)"}
                          </strong>
                          {p.grupa.opis && <span className="meta">{p.grupa.opis}</span>}
                        </span>
                        <span className="liczba-grupy">{osoby(p.grupa.ludzie.length)}</span>
                      </button>
                    </th>
                  </tr>
                ) : (
                  <tr
                    key={p.s.osoba.osoba_id}
                    className="wiersz-osoby"
                    tabIndex={0}
                    onClick={() => onWybierz(p.s.osoba)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") onWybierz(p.s.osoba);
                    }}
                  >
                    {kolumny.map((k) => (
                      <td key={k.id} className={`kol-${k.id}`} data-etykieta={k.id === "osoba" ? undefined : k.nazwa}>
                        {k.komorka(p.s)}
                      </td>
                    ))}
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}

      {strony.length > 1 && (
        <nav className="stronicowanie" aria-label="Strony tabeli">
          <button type="button" className="jasny" disabled={nr === 0} onClick={() => idzDo(nr - 1)}>
            <Ikona nazwa="wstecz" />
            Poprzednia
          </button>
          <span className="meta">
            Strona {nr + 1} z {strony.length}
          </span>
          <button type="button" className="jasny" disabled={nr === strony.length - 1} onClick={() => idzDo(nr + 1)}>
            Następna
            <Ikona nazwa="dalej" />
          </button>
        </nav>
      )}
    </div>
  );
}

/** Pigułka z własnym menu (zamiast natywnego select): Escape, klik obok albo wyjście fokusem zamyka. */
function Rozwijane({
  etykieta,
  aktywne,
  doPrawej,
  children,
}: {
  etykieta: string;
  aktywne?: boolean;
  doPrawej?: boolean;
  children: (zamknij: () => void) => ReactNode;
}) {
  const [otwarte, setOtwarte] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const przycisk = useRef<HTMLButtonElement>(null);
  const id = useId();
  const zamknij = () => {
    setOtwarte(false);
    przycisk.current?.focus();
  };

  useEffect(() => {
    if (!otwarte) return;
    const obok = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOtwarte(false);
    };
    const klawisz = (e: KeyboardEvent) => {
      if (e.key === "Escape") zamknij();
    };
    document.addEventListener("pointerdown", obok);
    document.addEventListener("keydown", klawisz);
    return () => {
      document.removeEventListener("pointerdown", obok);
      document.removeEventListener("keydown", klawisz);
    };
  }, [otwarte]);

  return (
    <div
      className={`rozwijane${doPrawej ? " do-prawej" : ""}`}
      ref={ref}
      onBlur={(e) => {
        if (!ref.current?.contains(e.relatedTarget as Node | null)) setOtwarte(false);
      }}
    >
      <button
        ref={przycisk}
        type="button"
        className={`pigulka${aktywne ? " aktywna" : ""}`}
        aria-expanded={otwarte}
        aria-controls={id}
        onClick={() => setOtwarte((o) => !o)}
      >
        {etykieta}
        <Ikona nazwa="dalej" rozmiar={16} />
      </button>
      {otwarte && (
        <div className="panel-rozwijany" id={id} role="group" aria-label={etykieta} tabIndex={-1}>
          {children(zamknij)}
        </div>
      )}
    </div>
  );
}

/** Plakietka terminu: czerwona po terminie, bursztynowa przy ≤ 14 dniach; dalej nic. */
export function PlakietkaTerminu({ s }: { s: Sprawa }) {
  const c = s.cykl;
  if (!c || c.dni_do_terminu === null) return null;
  if (c.po_terminie) return <span className="status negatywna">po terminie {dni(-c.dni_do_terminu)}</span>;
  if (c.dni_do_terminu === 0) return <span className="status uwaga">dziś</span>;
  if (c.dni_do_terminu <= 14) return <span className="status uwaga">za {dni(c.dni_do_terminu)}</span>;
  return null;
}
