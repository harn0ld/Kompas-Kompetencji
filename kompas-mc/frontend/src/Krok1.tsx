import { FormEvent, useEffect, useState } from "react";
import {
  BladApi,
  pobierzKrok1,
  pobierzProcesy,
  pobierzZrodla,
  rozpocznijProces,
  type AnalizaKroku1,
  type Brak,
  type Pracownik,
  type ProcesOceny,
  type Przeslanka,
  type Sciezka,
  type SourceRef,
} from "./api";
import { PoprzedniaOcena, zdanieOOsobie } from "./PoprzedniaOcena";
import { Zwijane } from "./Zwijane";
import { data } from "./zespol-dane";
import "./krok2.css";
import "./ocena.css";

export const NAZWA_SCIEZKI: Record<Sciezka, string> = { pierwsza: "pierwsza ocena", okresowa: "ocena okresowa" };

/** Nazwy kryteriów przychodzą z modelu wielkimi literami; na ekranie zdaniowo. */
export const nazwaKryterium = (n: string) => n.charAt(0).toUpperCase() + n.slice(1).toLowerCase();

/** Kategorie źródeł po ludzku: przepis, materiał (poradnik, model, OSP), zasada aplikacji. */
const KATEGORIE: Record<string, { tekst: string; klasa: string }> = {
  PRZEPIS: { tekst: "Przepis", klasa: "przepis" },
  "OBJAŚNIENIE_MATERIAŁU": { tekst: "Materiał", klasa: "" },
  DECYZJA_PROJEKTOWA: { tekst: "Zasada aplikacji", klasa: "zasada" },
  FUNKCJA_APLIKACJI: { tekst: "Instrukcja aplikacji", klasa: "zasada" },
  "BRAK_ŹRÓDŁA": { tekst: "Brak źródła", klasa: "typ-brak" },
};

/** Etykieta i klasa znacznika kategorii źródła; nieznana kategoria zostaje bez zmian. */
export const kategoriaZrodla = (k: string) => KATEGORIE[k] ?? { tekst: k, klasa: "" };

// Nazwy dokumentów z manifestu korpusu (/api/zrodla); pobierane raz na sesję.
let nazwyDokumentow: Promise<Record<string, string>> | null = null;
function useNazwyDokumentow(): Record<string, string> {
  const [nazwy, setNazwy] = useState<Record<string, string>>({});
  useEffect(() => {
    nazwyDokumentow ??= pobierzZrodla()
      .then((z) => Object.fromEntries(z.dokumenty.map((d) => [d.doc_id, d.nazwa])))
      .catch(() => ({}));
    let zyje = true;
    nazwyDokumentow.then((n) => zyje && setNazwy(n));
    return () => {
      zyje = false;
    };
  }, []);
  return nazwy;
}

export function Zrodla({ adnotacje }: { adnotacje: SourceRef[] }) {
  const nazwy = useNazwyDokumentow();
  return (
    <div className="zrodla">
      {adnotacje.map((a, i) => (
        <Zrodlo key={i} a={a} nazwy={nazwy} />
      ))}
    </div>
  );
}

function Zrodlo({ a, nazwy }: { a: SourceRef; nazwy: Record<string, string> }) {
  const [otwarte, setOtwarte] = useState(false);
  const cytat = a["cytat_dosłowny"];
  const strona = a.strona && a.lokalizator !== `s. ${a.strona}` ? `s. ${a.strona}` : null;
  const dokument = a.doc_id ? (nazwy[a.doc_id] ?? a.doc_id) : null;
  const miejsce = [dokument, a.lokalizator, strona].filter(Boolean).join(", ");
  const kategoria = kategoriaZrodla(a.kategoria);
  return (
    <div className="zrodlo">
      <span className={`kategoria ${kategoria.klasa}`}>{kategoria.tekst}</span>
      {miejsce}
      {cytat && (
        <button type="button" className="link" aria-expanded={otwarte} onClick={() => setOtwarte((v) => !v)}>
          {otwarte ? "ukryj cytat" : "cytat"}
        </button>
      )}
      {!cytat && a.uzasadnienie && <span>{a.uzasadnienie}</span>}
      {otwarte && cytat && <blockquote>{cytat}</blockquote>}
    </div>
  );
}

function Braki({ braki }: { braki: Brak[] }) {
  if (braki.length === 0) return null;
  return (
    <div className="brak">
      <strong>System nie zgaduje, brakuje danych:</strong>
      <ul>
        {braki.map((b) => (
          <li key={b.pole}>{b.komunikat}</li>
        ))}
      </ul>
    </div>
  );
}

function Przeslanki({ przeslanki }: { przeslanki: Przeslanka[] }) {
  return (
    <ul className="przeslanki">
      {przeslanki.map((p) => (
        <li key={p.id}>
          <div className="wiersz-przeslanki">
            {p.spelniona === null && <span className="status uwaga">brak danych</span>}
            <span>{p.opis}</span>
          </div>
          <Zrodla adnotacje={p.adnotacje} />
        </li>
      ))}
    </ul>
  );
}

/** Powód z API (tekst, `komunikat` albo lista z walidacji); stałe teksty tylko, gdy API go nie poda (#76). */
export function opisBledu(err: unknown): string {
  if (!(err instanceof BladApi)) return "Brak połączenia z API.";
  if (err.status === 403) return "Nie masz uprawnień do tej czynności.";
  const d = err.detail as unknown;
  if (typeof d === "string" && d) return d;
  if (Array.isArray(d)) return d.map((b) => (typeof b === "string" ? b : (b?.komunikat ?? b?.msg ?? JSON.stringify(b)))).join(" ");
  const komunikat = (d as { komunikat?: unknown } | null)?.komunikat;
  if (typeof komunikat === "string" && komunikat) return komunikat;
  if (err.status === 409) return "Tej czynności nie można teraz wykonać.";
  if (err.status === 422) return "Dane nie pozwalają wykonać tej czynności.";
  return `Błąd API ${err.status}.`;
}

function Rozpoczecie({
  token,
  analiza,
  onRozpoczeto,
}: {
  token: string;
  analiza: AnalizaKroku1;
  onRozpoczeto: (p: ProcesOceny) => void;
}) {
  const proponowana = analiza.sciezka.proponowana;
  const [sciezka, setSciezka] = useState<Sciezka | null>(proponowana);
  const [uzasadnienie, setUzasadnienie] = useState("");
  const [czekam, setCzekam] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);

  const inna = sciezka !== proponowana;
  const brakArkusza = sciezka === "okresowa" && !analiza.arkusz_okresowy.arkusz;
  const gotowe = sciezka !== null && !brakArkusza && (!inna || uzasadnienie.trim() !== "");

  async function wyslij(e: FormEvent) {
    e.preventDefault();
    if (!sciezka) return;
    setCzekam(true);
    setBlad(null);
    try {
      onRozpoczeto(
        await rozpocznijProces(token, {
          osoba_id: analiza.osoba_id,
          sciezka,
          uzasadnienie: inna ? uzasadnienie.trim() : null,
        }),
      );
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setCzekam(false);
    }
  }

  return (
    <form className="k1-start" onSubmit={wyslij}>
      <p className="meta">Decyzję podejmujesz Ty. Rozpoczęcie zapisuje się w dzienniku zmian.</p>
      <div className="wybor" role="group" aria-label="Ścieżka oceny">
        {(["pierwsza", "okresowa"] as Sciezka[]).map((s) => (
          <button key={s} type="button" aria-pressed={sciezka === s} onClick={() => setSciezka(s)}>
            {NAZWA_SCIEZKI[s]}
            {s === proponowana && " (propozycja)"}
          </button>
        ))}
      </div>
      {brakArkusza && <p className="brak">Nie ustalono arkusza B ani C. Uzupełnij dane kadrowe.</p>}
      {sciezka && inna && (
        <label className="etykieta">
          {proponowana ? "Dlaczego inna ścieżka niż proponowana" : "Uzasadnienie wyboru ścieżki"} (wymagane)
          <textarea value={uzasadnienie} onChange={(e) => setUzasadnienie(e.target.value)} rows={2} />
        </label>
      )}
      <button disabled={czekam || !gotowe}>{czekam ? "Rozpoczynam…" : "Rozpocznij ocenę"}</button>
      {blad && <p className="blad">{blad}</p>}
    </form>
  );
}

/** Ścieżka i arkusz jednym zdaniem; przesłanki i przepisy po rozwinięciu. */
function Decyzja({ analiza }: { analiza: AnalizaKroku1 }) {
  const [otwarte, setOtwarte] = useState(false);
  const [pozostale, setPozostale] = useState(false);
  const s = analiza.sciezka;
  const a = analiza.arkusz_okresowy;
  const okresowa = s.proponowana === "okresowa";
  const spelnione = s.przeslanki.filter((p) => p.spelniona !== false);
  const nieDotyczy = s.przeslanki.filter((p) => p.spelniona === false);
  const uwagi = [...new Set(s.przeslanki.map((p) => p.uwaga).filter(Boolean))];
  const tytul = s.proponowana
    ? `${NAZWA_SCIEZKI[s.proponowana].charAt(0).toUpperCase()}${NAZWA_SCIEZKI[s.proponowana].slice(1)}${okresowa && a.arkusz ? ` · arkusz ${a.arkusz}` : ""}`
    : "Ścieżki nie można ustalić";

  return (
    <div className="k1-blok">
      <h2>Jak oceniamy</h2>
      <div className="k1-decyzja">
        <p className="k1-tytul">{tytul}</p>
        <p className="meta">Propozycja z danych kadrowych. Potwierdzasz ją, rozpoczynając ocenę.</p>
      </div>
      <Braki braki={[...s.braki, ...(okresowa ? a.braki : [])]} />
      {analiza.arkusz_a.dotyczy && <p className="brak">{analiza.arkusz_a.komunikat}</p>}
      <button type="button" className="link k1-rozwin" aria-expanded={otwarte} onClick={() => setOtwarte((v) => !v)}>
        {otwarte ? "Ukryj przepisy" : "Dlaczego? Przepisy i przesłanki"}
      </button>
      <Zwijane otwarte={otwarte}>
        <div className="k1-szczegoly">
          {okresowa && a.arkusz && <p>{a.uzasadnienie}</p>}
          <Przeslanki przeslanki={spelnione} />
          {okresowa && a.arkusz && <Zrodla adnotacje={a.adnotacje} />}
          {nieDotyczy.length > 0 && (
            <>
              <button type="button" className="link k1-rozwin" aria-expanded={pozostale} onClick={() => setPozostale((v) => !v)}>
                {pozostale ? "Ukryj przesłanki, które nie dotyczą" : `Nie dotyczy tej osoby (${nieDotyczy.length})`}
              </button>
              <Zwijane otwarte={pozostale}>
                <Przeslanki przeslanki={nieDotyczy} />
              </Zwijane>
            </>
          )}
          {uwagi.map((u) => (
            <p key={u} className="meta">
              {u === "brak tekstu ustawy w bazie"
                ? "Ustawy o służbie cywilnej nie ma w materiałach; artykuły podajemy za poradnikiem."
                : u}
            </p>
          ))}
        </div>
      </Zwijane>
    </div>
  );
}

/** OSP: cel i zadania dominujące skrócone do dwóch linii; całość po rozwinięciu. */
function OpisStanowiska({ analiza }: { analiza: AnalizaKroku1 }) {
  const [caly, setCaly] = useState(false);
  const osp = analiza.osp;
  if (!osp) {
    return (
      <div className="k1-blok">
        <h2>Opis stanowiska</h2>
        <p className="meta">Brak OSP tej osoby w materiałach. Ścieżka i arkusz wynikają z danych kadrowych (QNT).</p>
      </div>
    );
  }
  const zadania = (lista: typeof osp.zadania_dominujace) => (
    <ol className={`k1-zadania ${caly ? "" : "skrocone"}`}>
      {lista.map((z) => (
        <li key={z.nr} value={z.nr}>
          <span className="k1-zadanie">{z.tekst}</span>
          {caly && <Zrodla adnotacje={[z.adnotacja]} />}
        </li>
      ))}
    </ol>
  );
  return (
    <div className="k1-blok">
      <h2>Opis stanowiska</h2>
      <p className="meta">
        {osp.nazwa} · {osp.komorka.join(" / ")}
      </p>
      <p>{osp.cel.tekst}</p>
      <p className="etykieta">Zadania dominujące</p>
      {zadania(osp.zadania_dominujace)}
      <Zwijane otwarte={caly}>
        <div className="k1-szczegoly">
          <Zrodla adnotacje={[osp.cel.adnotacja]} />
          {osp.zadania_pozostale.length > 0 && (
            <>
              <p className="etykieta">Pozostałe zadania</p>
              {zadania(osp.zadania_pozostale)}
            </>
          )}
          <p className="etykieta">Złożoność i kreatywność</p>
          <p>{osp.zlozonosc.opis.tekst}</p>
          <Zrodla adnotacje={[osp.zlozonosc.opis.adnotacja]} />
          <p className="etykieta">Samodzielność i inicjatywa</p>
          <p>{osp.samodzielnosc.opis.tekst}</p>
          <Zrodla adnotacje={[osp.samodzielnosc.opis.adnotacja]} />
          <p className="etykieta">Podlegli pracownicy</p>
          <p>{osp.podlegli.zaznaczone}</p>
        </div>
      </Zwijane>
      <button type="button" className="link k1-rozwin" aria-expanded={caly} onClick={() => setCaly((v) => !v)}>
        {caly ? "Zwiń opis stanowiska" : "Cały opis stanowiska"}
      </button>
    </div>
  );
}

export function Krok1({
  token,
  osoba,
  moznaProwadzic,
  onWroc,
  onDalej,
}: {
  token: string;
  osoba: Pracownik;
  moznaProwadzic: boolean;
  onWroc: () => void;
  onDalej: (p: ProcesOceny) => void;
}) {
  const [analiza, setAnaliza] = useState<AnalizaKroku1 | null>(null);
  const [proces, setProces] = useState<ProcesOceny | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([pobierzKrok1(token, osoba.osoba_id), pobierzProcesy(token)])
      .then(([a, procesy]) => {
        setAnaliza(a);
        setProces(procesy.find((p) => p.osoba_id === osoba.osoba_id && p.status === "W_TOKU") ?? null);
      })
      .catch((err) =>
        setBlad(String(err).includes("403") ? "Nie masz dostępu do oceny tej osoby." : "Nie udało się pobrać analizy kroku 1."),
      );
  }, [token, osoba.osoba_id]);


  const wydzial = osoba.komorka.split(" / ").pop();

  return (
    <div className="k2">
      <div className="k2-naglowek">
        <button type="button" className="link" onClick={onWroc}>
          Wróć
        </button>
        <p className="meta">Rozpoczęcie oceny · zanim ocenisz</p>
        <h1>
          {osoba.imie} {osoba.nazwisko}
        </h1>
        <p className="opis">
          {osoba.stanowisko} · {wydzial}
        </p>
      </div>
      {blad && <p className="blad">{blad}</p>}
      {!blad && !analiza && <p className="meta">Wczytuję analizę…</p>}

      {analiza && (
        <div className="dwie">
          <div className="sekcja k1-glowna">
            <p className="k1-streszczenie">{zdanieOOsobie(osoba)}</p>
            <OpisStanowiska analiza={analiza} />
            <Decyzja analiza={analiza} />
            {/* Przy pierwszej ocenie poprzedniej nie ma, więc sekcji nie pokazujemy (Karol 22.11). */}
            {osoba.ostatnia_ocena_okresowa && <PoprzedniaOcena token={token} osoba={osoba} />}
            {/* Uwagi analizy to notatki o materiałach (np. kroki dodane z przepisu): są w „Źródłach i brakach”,
                tu tylko zaśmiecały ekran przełożonego (Karol 22.11: „jasno albo wcale”). */}
          </div>

          <aside className="sekcja k2-boczna">
            <div className="k2-podsumowanie">
              <h2>Następny krok</h2>
              {proces ? (
                <>
                  <p className="k1-tytul">Kryteria i wskaźniki</p>
                  <p className="meta">
                    {NAZWA_SCIEZKI[proces.sciezka].charAt(0).toUpperCase() + NAZWA_SCIEZKI[proces.sciezka].slice(1)} w toku od{" "}
                    {data(proces.rozpoczeto)}.
                  </p>
                  <button type="button" className="k2-zatwierdz" onClick={() => onDalej(proces)}>
                    Dalej: krok 2
                  </button>
                </>
              ) : moznaProwadzic ? (
                <Rozpoczecie token={token} analiza={analiza} onRozpoczeto={onDalej} />
              ) : (
                <p className="meta">Ocenę rozpoczyna przełożony.</p>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
