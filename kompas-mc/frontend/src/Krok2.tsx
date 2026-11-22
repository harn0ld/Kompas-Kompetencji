import { FormEvent, type ReactNode, useEffect, useState } from "react";
import {
  BladApi,
  pobierzCykl,
  pobierzCzescIPdf,
  pobierzKrok2,
  zapiszKrok2,
  type EtapOsoby,
  type Krok2 as DaneKroku2,
  type KryteriumKroku2,
  type Pracownik,
  type ProcesOceny,
  type SourceRef,
} from "./api";
import { NAZWA_SCIEZKI, Zrodla, opisBledu } from "./Krok1";
import { Ikona } from "./Ikona";
import { RozmowaWstepna } from "./RozmowaWstepna";
import { zapiszPlik } from "./Wynik";
import { ZakonczenieCzesciI } from "./CzescI";
import { data, odmiana } from "./zespol-dane";
import "./krok2.css";

type Wskazniki = Record<string, string[]>;

/** Etap cyklu osoby z /api/cykl; null, gdy API nie odpowiedziało albo nie zna osoby. */
const etapOsoby = (token: string, osobaId: string): Promise<EtapOsoby | null> =>
  pobierzCykl(token)
    .then((lista) => lista.find((e) => e.osoba_id === osobaId) ?? null)
    .catch(() => null);

/** Komunikat z API (tekst albo pole „komunikat”), inaczej ogólny opis błędu. */
function komunikatApi(err: unknown): string {
  const d = err instanceof BladApi ? err.detail : null;
  if (typeof d === "string") return d;
  const { komunikat, braki_terminu = [] } = (d ?? {}) as { komunikat?: string; braki_terminu?: string[] };
  return komunikat ? [komunikat, ...braki_terminu].join(" ") : opisBledu(err);
}

const dzisiaj = () => new Date().toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit", year: "numeric" });

function poczatek(d: DaneKroku2): { dodatkowe: string[]; wskazniki: Wskazniki } {
  if (d.wybor) {
    return {
      dodatkowe: d.wybor.kryteria.filter((k) => k.rodzaj === "DODATKOWE").map((k) => k.kompetencja_id),
      wskazniki: Object.fromEntries(d.wybor.kryteria.map((k) => [k.kompetencja_id, k.wskazniki.map((w) => w.id)])),
    };
  }
  const wskazniki: Wskazniki = {};
  for (const k of d.kryteria.filter((k) => k.rodzaj === "OBOWIAZKOWE")) wskazniki[k.kompetencja_id] = domyslne(k);
  return { dodatkowe: [], wskazniki };
}

/** Wskaźniki dopasowane do zadań z OSP; gdy żaden nie pasuje, wszystkie, żeby kryterium nie było puste. */
function domyslne(k: KryteriumKroku2): string[] {
  const pasujace = k.wskazniki.filter((w) => w.proponowany).map((w) => w.wskaznik_id);
  return pasujace.length > 0 ? pasujace : k.wskazniki.map((w) => w.wskaznik_id);
}

/** Źródła wskaźników kryterium bez powtórzeń: zwykle wszystkie stoją na tym samym miejscu rozporządzenia. */
function zrodlaKryterium(k: KryteriumKroku2): SourceRef[] {
  const widziane = new Set<string>();
  return k.wskazniki
    .map((w) => w.podstawa)
    .filter((a) => {
      const klucz = `${a.doc_id}|${a.lokalizator}|${a.strona}`;
      if (widziane.has(klucz)) return false;
      widziane.add(klucz);
      return true;
    });
}

/** Cicha linia wskaźników w wierszu kryterium: ile i skąd, bez „X z Y”, które myli się z liczbą kryteriów. */
function opisWskaznikow(k: KryteriumKroku2, wybrane: string[]): string {
  const n = wybrane.length;
  if (n === 0) return "Nie wybrano żadnego wskaźnika";
  const system = domyslne(k);
  const jakSystem = n === system.length && system.every((id) => wybrane.includes(id));
  if (!jakSystem) return `${n} ${odmiana(n, "wskaźnik wybrany", "wskaźniki wybrane", "wskaźników wybranych")} ręcznie`;
  if (k.wskazniki.some((w) => w.proponowany)) {
    return `${n} ${odmiana(n, "wskaźnik", "wskaźniki", "wskaźników")}`;
  }
  return `${n} ${odmiana(n, "wskaźnik", "wskaźniki", "wskaźników")} (wszystkie)`;
}

type PropsKryterium = {
  k: KryteriumKroku2;
  wybrane: string[];
  tylkoOdczyt: boolean;
  otwarte: boolean;
  onPrzelacz: () => void;
  onWskaznik: (id: string) => void;
  /** Kryterium dodatkowe: cały nagłówek wiersza wybiera albo odznacza kryterium. */
  dodatkowe?: { wybrane: boolean; zablokowane: boolean; onWybierz: () => void };
};

/** Wiersz kryterium (wzór makiety v2): obowiązkowe ze stałym znakiem, dodatkowe z kółkiem wyboru.
 *  Wskaźniki dobiera system; w wierszu tylko cicha linia i łącze do zmiany. */
function Kryterium({ k, wybrane, tylkoOdczyt, otwarte, onPrzelacz, onWskaznik, dodatkowe }: PropsKryterium) {
  const aktywne = !dodatkowe || dodatkowe.wybrane;
  const nazwa = (
    <span className="k2-nazwa">
      {k.nazwa.charAt(0) + k.nazwa.slice(1).toLowerCase()}
      {k.propozycja && (
        <span className="status uwaga" title={k.propozycja.powody.join("; ")}>
          propozycja systemu
        </span>
      )}
    </span>
  );
  return (
    <div className={`k2-wiersz ${dodatkowe?.wybrane ? "wybrany" : ""} ${dodatkowe?.zablokowane ? "zablokowany" : ""} ${otwarte && aktywne ? "otwarty" : ""}`}>
      {dodatkowe ? (
        <button
          type="button"
          role="checkbox"
          aria-checked={dodatkowe.wybrane}
          className="k2-glowa"
          disabled={tylkoOdczyt || dodatkowe.zablokowane}
          onClick={dodatkowe.onWybierz}
        >
          <span className="k2-znak kolo">{dodatkowe.wybrane && <Ikona nazwa="ok" rozmiar={16} />}</span>
          {nazwa}
        </button>
      ) : (
        <div className="k2-glowa">
          <span className="k2-znak">
            <Ikona nazwa="ok" rozmiar={20} />
          </span>
          {nazwa}
        </div>
      )}
      {aktywne ? (
        <p className="k2-linia">
          <span className={wybrane.length === 0 ? "blad" : undefined}>{opisWskaznikow(k, wybrane)}</span>
          <button type="button" className="link" aria-expanded={otwarte} onClick={onPrzelacz}>
            {otwarte ? "Zwiń wskaźniki" : tylkoOdczyt ? "Pokaż wskaźniki" : "Zmień wskaźniki"}
          </button>
        </p>
      ) : null}
      {otwarte && aktywne && (
        <div className="k2-cialo">
          <ul className="k2-wskazniki">
            {k.wskazniki.map((w) => (
              <li key={w.wskaznik_id}>
                <label className="zaznacz">
                  <input
                    type="checkbox"
                    checked={wybrane.includes(w.wskaznik_id)}
                    disabled={tylkoOdczyt}
                    onChange={() => onWskaznik(w.wskaznik_id)}
                  />
                  <span>
                    {w.nazwa}
                    {w.zadania.length > 0 && (
                      <span className="k2-zadania" title={w.zadania.map((z) => `${z.nr}. ${z.tekst}`).join("\n")}>
                        zadania z OSP: {w.zadania.map((z) => z.nr).join(", ")}
                      </span>
                    )}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <Zrodla adnotacje={[...zrodlaKryterium(k), ...(k.propozycja?.adnotacje ?? [])]} />
        </div>
      )}
    </div>
  );
}

/** Sekcja kryteriów: tytuł z liczbą, z prawej podstawa prawna, która rozwija cytat. */
function Sekcja({
  tytul,
  liczba,
  podstawa,
  children,
}: {
  tytul: string;
  liczba?: string;
  podstawa: SourceRef[];
  children: ReactNode;
}) {
  const [cytat, setCytat] = useState(false);
  return (
    <section className="k2-sekcja">
      <div className="k2-sekcja-glowa">
        <h2>
          {tytul} {liczba && <span className="k2-liczba">{liczba}</span>}
        </h2>
        {podstawa[0] && (
          <button type="button" className="k2-podstawa" aria-expanded={cytat} onClick={() => setCytat((v) => !v)}>
            <Ikona nazwa="dokument" rozmiar={16} />
            {podstawa[0].lokalizator}
          </button>
        )}
      </div>
      {cytat && <Zrodla adnotacje={podstawa} />}
      {children}
    </section>
  );
}

export function Krok2({
  token,
  osoba,
  proces,
  moznaProwadzic,
  onWstecz,
  onDalej,
  onPracownik,
}: {
  token: string;
  osoba: Pracownik;
  proces: ProcesOceny;
  moznaProwadzic: boolean;
  onWstecz: () => void;
  onDalej: () => void;
  onPracownik: () => void;
}) {
  const [dane, setDane] = useState<DaneKroku2 | null>(null);
  const [cykl, setCykl] = useState<EtapOsoby | null>(null);
  const [dodatkowe, setDodatkowe] = useState<string[]>([]);
  const [wskazniki, setWskazniki] = useState<Wskazniki>({});
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  const [drukuje, setDrukuje] = useState(false);
  /** Dzień zapisu (dd.mm.rrrr), gdy po zapisie okres oceny dopiero się zaczyna; wtedy nie idziemy do kroków 3–5. */
  const [ustalone, setUstalone] = useState<string | null>(null);
  /** Wybór różni się od zapisanego; bez zmian ponowny zapis przesunąłby datę ustalenia kryteriów. */
  const [zmieniono, setZmieniono] = useState(false);
  const [otwarte, setOtwarte] = useState<string[]>([]);
  const [pozostale, setPozostale] = useState(false);
  const [metodyka, setMetodyka] = useState(false);

  useEffect(() => {
    pobierzKrok2(token, proces.id)
      .then((d) => {
        const p = poczatek(d);
        setDane(d);
        setDodatkowe(p.dodatkowe);
        setWskazniki(p.wskazniki);
      })
      .catch((err) => setBlad(opisBledu(err)));
    etapOsoby(token, osoba.osoba_id).then(setCykl);
  }, [token, proces.id, osoba.osoba_id]);

  if (!dane) {
    return (
      <section>
        {blad ? <p className="blad">{blad}</p> : <p className="meta">Wczytuję kryteria…</p>}
      </section>
    );
  }

  const tylkoOdczyt = !moznaProwadzic;
  const obowiazkowe = dane.kryteria.filter((k) => k.rodzaj === "OBOWIAZKOWE");
  const proponowane = dane.kryteria.filter((k) => k.rodzaj === "DODATKOWE_PROPONOWANE");
  const dostepne = dane.kryteria.filter((k) => k.rodzaj === "DODATKOWE_DOSTEPNE");
  const wybrane = [...obowiazkowe.map((k) => k.kompetencja_id), ...dodatkowe];
  const pusteKryteria = wybrane.filter((id) => (wskazniki[id] ?? []).length === 0);

  function przelaczWskaznik(kompetencja: string, id: string) {
    setUstalone(null);
    setZmieniono(true);
    setWskazniki((w) => {
      const obecne = w[kompetencja] ?? [];
      return { ...w, [kompetencja]: obecne.includes(id) ? obecne.filter((x) => x !== id) : [...obecne, id] };
    });
  }

  function przelaczDodatkowe(k: KryteriumKroku2) {
    setUstalone(null);
    setZmieniono(true);
    if (dodatkowe.includes(k.kompetencja_id)) {
      setDodatkowe((d) => d.filter((x) => x !== k.kompetencja_id));
    } else {
      setDodatkowe((d) => [...d, k.kompetencja_id]);
      setWskazniki((w) => ({ ...w, [k.kompetencja_id]: w[k.kompetencja_id] ?? domyslne(k) }));
    }
  }

  async function zapisz(e: FormEvent) {
    e.preventDefault();
    setCzekam(true);
    setBlad(null);
    try {
      if (!dane?.wybor || zmieniono) {
        const po = await zapiszKrok2(token, proces.id, {
          dodatkowe,
          wskazniki: Object.fromEntries(wybrane.map((id) => [id, wskazniki[id] ?? []])),
        });
        setDane((d) => (d && po.krok2 ? { ...d, wybor: po.krok2 } : d));
        setZmieniono(false);
      }
    } catch (err) {
      setBlad(
        err instanceof BladApi && err.status === 409
          ? "Proces oceny nie jest w toku, więc wyboru nie można zapisać."
          : opisBledu(err),
      );
      setCzekam(false);
      return;
    }
    // Kryteria ustala się na początku okresu, ocenia po jego końcu (rozp. 2016 § 5–7, § 10–11):
    // do kroków 3–5 prowadzi tylko etap „ocena”, także gdy cyklu nie udało się wczytać (#25).
    const etap = await etapOsoby(token, osoba.osoba_id);
    setCykl(etap);
    setCzekam(false);
    // Okresowa: część I kończy się zapisaną datą zapoznania z kryteriami (§ 6 ust. 2), także na końcu okresu.
    if (etap?.etap === "ocena" && proces.sciezka !== "okresowa") onDalej();
    else setUstalone(etap?.kryteria_ustalone ? data(etap.kryteria_ustalone) : dzisiaj());
  }

  async function drukuj() {
    setDrukuje(true);
    setBlad(null);
    try {
      zapiszPlik(await pobierzCzescIPdf(token, proces.id), `arkusz-${proces.arkusz}-${proces.id}-czesc-I.pdf`);
    } catch (err) {
      setBlad(komunikatApi(err));
    } finally {
      setDrukuje(false);
    }
  }

  const przelaczOtwarte = (id: string) => setOtwarte((o) => (o.includes(id) ? o.filter((x) => x !== id) : [...o, id]));
  const wiersz = (k: KryteriumKroku2, dodatkoweKryterium: boolean) => {
    const wybrany = dodatkowe.includes(k.kompetencja_id);
    return (
      <Kryterium
        key={k.kompetencja_id}
        k={k}
        wybrane={wskazniki[k.kompetencja_id] ?? []}
        tylkoOdczyt={tylkoOdczyt}
        otwarte={otwarte.includes(k.kompetencja_id)}
        onPrzelacz={() => przelaczOtwarte(k.kompetencja_id)}
        onWskaznik={(id) => przelaczWskaznik(k.kompetencja_id, id)}
        dodatkowe={
          dodatkoweKryterium
            ? {
                wybrane: wybrany,
                zablokowane: !wybrany && dodatkowe.length >= dane.limit_dodatkowych,
                onWybierz: () => przelaczDodatkowe(k),
              }
            : undefined
        }
      />
    );
  };
  const nazwaArkusza = dane.arkusz === "PIERWSZA" ? "pierwszej oceny" : dane.arkusz;
  // Podgląd bez prawa prowadzenia: zapisany wybór prowadzi dalej tylko w etapie oceny, wcześniej pokazuje stan.
  const podgladUstalonych =
    tylkoOdczyt && dane.wybor && cykl?.etap !== "ocena" ? data(cykl?.kryteria_ustalone ?? dane.wybor.zapisano) : null;
  // Część I zakończona (data zapoznania zapisana): przy powrocie widać jej zakończenie, nie formularz od nowa.
  const ustalonoDnia = ustalone ?? podgladUstalonych ?? (dane.wybor?.zapoznanie ? data(dane.wybor.zapisano) : null);

  return (
    <div className="k2 k2-kryteria">
      <div className="k2-naglowek">
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do kroku 1
        </button>
        <p className="meta">Rozpoczęcie oceny · kryteria (część I arkusza)</p>
        <h1>Kryteria i wskaźniki</h1>
        <p className="opis">
          {osoba.imie} {osoba.nazwisko} · {NAZWA_SCIEZKI[dane.sciezka]} · arkusz {nazwaArkusza}
        </p>
      </div>

      {tylkoOdczyt && !dane.wybor && (
        <p className="brak">Przełożony nie zatwierdził jeszcze kryteriów. Zaznaczenia to propozycja systemu.</p>
      )}
      {!tylkoOdczyt && !dane.wybor && proces.sciezka === "okresowa" && cykl?.etap === "ocena" && (
        <p className="meta">Zaznacz kryteria dodatkowe z podpisanej części I (§ 9 ust. 3).</p>
      )}

      {/* Karol 02:04: pół na pół, obowiązkowe z lewej na dwie kolumny, dodatkowe z prawej, na jednym ekranie.
          Pierwsza ocena nie ma dodatkowych (limit 0), więc obowiązkowe zajmują całą szerokość. */}
      <div className={dane.limit_dodatkowych > 0 ? "k2-kolumny" : undefined}>
        <Sekcja tytul="Obowiązkowe" liczba={String(obowiazkowe.length)} podstawa={dane.podstawa_obowiazkowych}>
          <div className="k2-lista k2-dwie">{obowiazkowe.map((k) => wiersz(k, false))}</div>
        </Sekcja>

        {dane.limit_dodatkowych > 0 && (
          <Sekcja
            tytul="Dodatkowe"
            liczba={`wybrane ${dodatkowe.length} · od 0 do ${dane.limit_dodatkowych}`}
            podstawa={dane.podstawa_dodatkowych}
          >
            <div className="k2-lista">
              {proponowane.map((k) => wiersz(k, true))}
              {pozostale && dostepne.map((k) => wiersz(k, true))}
            </div>
            {dostepne.length > 0 && (
              <button type="button" className="link k2-pozostale" aria-expanded={pozostale} onClick={() => setPozostale((v) => !v)}>
                {pozostale ? "Ukryj pozostałe kompetencje" : `Pozostałe kompetencje (${dostepne.length})`}
              </button>
            )}
          </Sekcja>
        )}
      </div>

      <div className="k2-metodyka">
        <button type="button" className="link" aria-expanded={metodyka} onClick={() => setMetodyka((v) => !v)}>
          {metodyka ? "Ukryj, jak system dobrał wskaźniki" : "Jak system dobrał wskaźniki?"}
        </button>
        {metodyka && (
          <>
            <p>
              <span className="status uwaga">{dane.metodyka.status}</span>
            </p>
            <p className="meta">{dane.metodyka.opis}</p>
            <Zrodla adnotacje={[...dane.metodyka.adnotacje, ...dane.podstawa_obowiazkowych, ...dane.podstawa_dodatkowych]} />
          </>
        )}
      </div>

      <div className="k2-pasek">
        {ustalonoDnia ? (
          proces.sciezka === "okresowa" && dane.wybor ? (
            <ZakonczenieCzesciI
              token={token}
              proces={proces}
              wybor={dane.wybor}
              cykl={cykl}
              moznaProwadzic={moznaProwadzic}
              onZapisano={(po) => setDane((d) => (d && po.krok2 ? { ...d, wybor: po.krok2 } : d))}
              onDalej={onDalej}
              onPracownik={onPracownik}
              demo={Boolean(osoba.demo_od_poczatku)}
            />
          ) : proces.sciezka === "pierwsza" ? (
            <RozmowaWstepna token={token} procesId={proces.id} moznaProwadzic={moznaProwadzic} onPracownik={onPracownik} />
          ) : (
            <div className="k2-ustalone" role="status">
              <p className="sukces">
                <strong>Kryteria ustalone {ustalonoDnia}</strong>
                {cykl?.termin && ` · ${cykl.termin.nazwa} do ${data(cykl.termin.data)}`}
              </p>
              {cykl?.etap === "brak_danych" && cykl.braki.length > 0 && (
                <p className="meta">Termin oceny ustalisz po uzupełnieniu danych kadrowych: {cykl.braki.join(" ")}</p>
              )}
              <div className="k2-akcje">
                <button type="button" className="link k2-do-pracownika" onClick={onPracownik}>
                  Wróć do pracownika
                </button>
                {moznaProwadzic && proces.sciezka === "okresowa" && cykl?.etap !== "brak_danych" && (
                  <button type="button" disabled={drukuje} onClick={drukuj}>
                    {drukuje ? "Przygotowuję PDF…" : "Wydrukuj część I do podpisu"}
                  </button>
                )}
              </div>
              {proces.sciezka === "okresowa" && (
                <p className="meta">
                  Po podpisie ocenianego oryginał arkusza trafia do akt osobowych, a kopię części I doręczasz ocenianemu (§ 6 ust. 3).
                </p>
              )}
              {blad && <p className="blad">{blad}</p>}
            </div>
          )
        ) : (
          <>
            {dane.wybor && (
              <p className="meta">
                Zapisany wybór: {dane.wybor.kryteria.length} kryteriów, zapisał {dane.wybor.zapisal}.
              </p>
            )}
            {moznaProwadzic && pusteKryteria.length > 0 && (
              <p className="blad">Każde wybrane kryterium musi mieć co najmniej jeden wskaźnik.</p>
            )}
            {blad && <p className="blad">{blad}</p>}
            <div className="k2-akcje">
              {moznaProwadzic && (
                <form onSubmit={zapisz}>
                  <button disabled={czekam || pusteKryteria.length > 0}>
                    {czekam ? "Zapisuję…" : "Zatwierdź kryteria i dalej"}
                  </button>
                </form>
              )}
              {tylkoOdczyt && dane.wybor && cykl?.etap === "ocena" && (
                <button type="button" onClick={onDalej}>
                  Dalej: rozmowa oceniająca
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
