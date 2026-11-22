import { FormEvent, useEffect, useRef, useState } from "react";
import { pytajAsystenta, type CytatAsystenta, type OdpowiedzAsystenta, type Sciezka } from "./api";
import { kategoriaZrodla } from "./Krok1";

/**
 * Czat asystenta formalnego (#37). Komponent do osadzenia na ekranie każdej ścieżki:
 * `<AsystentFormalny sciezka="pierwsza" />` filtruje źródła do tej ścieżki; bez `sciezka`
 * użytkownik wybiera ją sam. Asystent tylko wskazuje źródła – nie ocenia.
 * `pytanieZZewnatrz` wysyła pytanie zadane poza czatem (pole na pulpicie); nowe `id` = nowe pytanie.
 */
interface Props {
  sciezka?: Sciezka;
  przyklady?: string[];
  pytanieZZewnatrz?: { id: number; tekst: string } | null;
}

interface Wymiana {
  id: number;
  pytanie: string;
  sciezka: Sciezka | null;
  odpowiedz?: OdpowiedzAsystenta;
  blad?: string;
}

const NAZWA_SCIEZKI: Record<Sciezka, string> = { pierwsza: "pierwsza ocena", okresowa: "ocena okresowa" };
const WYBOR_SCIEZKI: { wartosc: Sciezka | ""; nazwa: string }[] = [
  { wartosc: "", nazwa: "obie" },
  { wartosc: "pierwsza", nazwa: NAZWA_SCIEZKI.pierwsza },
  { wartosc: "okresowa", nazwa: NAZWA_SCIEZKI.okresowa },
];

export default function AsystentFormalny({ sciezka, przyklady = [], pytanieZZewnatrz }: Props) {
  const [pytanie, setPytanie] = useState("");
  const [wybrana, setWybrana] = useState<Sciezka | "">(sciezka ?? "");
  const [rozmowa, setRozmowa] = useState<Wymiana[]>([]);
  const [czekam, setCzekam] = useState(false);
  const aktywna: Sciezka | null = sciezka ?? (wybrana || null);
  const ostatnie = useRef<HTMLLIElement>(null);

  // Nowe pytanie (i jego odpowiedź, gdy przyjdzie) przewija rozmowę do siebie, żeby odpowiedź czytać od początku.
  const ostatnia = rozmowa[rozmowa.length - 1];
  const gotowa = !!(ostatnia?.odpowiedz || ostatnia?.blad);
  useEffect(() => {
    const ruch = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    ostatnie.current?.scrollIntoView({ block: "start", behavior: ruch });
  }, [rozmowa.length, gotowa]);

  async function zapytaj(tekst: string) {
    const t = tekst.trim();
    if (!t || czekam) return;
    const id = Date.now();
    setRozmowa((r) => [...r, { id, pytanie: t, sciezka: aktywna }]);
    setPytanie("");
    setCzekam(true);
    try {
      // Jak historia czatu w STAGO: dopytanie idzie razem z ostatnim pytaniem, na które była odpowiedź.
      const poprzednie = [...rozmowa].reverse().find((w) => w.odpowiedz?.znaleziono)?.pytanie;
      const odp = await pytajAsystenta(t, aktywna, poprzednie);
      setRozmowa((r) => r.map((w) => (w.id === id ? { ...w, odpowiedz: odp } : w)));
    } catch (err) {
      setRozmowa((r) => r.map((w) => (w.id === id ? { ...w, blad: String(err) } : w)));
    } finally {
      setCzekam(false);
    }
  }

  // Każde pytanie z zewnątrz wysyłamy raz (StrictMode uruchamia efekt podwójnie).
  const wyslane = useRef<number | null>(null);
  useEffect(() => {
    if (!pytanieZZewnatrz || wyslane.current === pytanieZZewnatrz.id) return;
    wyslane.current = pytanieZZewnatrz.id;
    void zapytaj(pytanieZZewnatrz.tekst);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pytanieZZewnatrz?.id]);

  function wyslij(e: FormEvent) {
    e.preventDefault();
    void zapytaj(pytanie);
  }

  return (
    <div className="czat">
      {rozmowa.length === 0 && (
        <p className="opis">
          Odpowiada wyłącznie na podstawie materiałów MC i zawsze pokazuje źródło. Nie ocenia pracownika
          – decyzja należy do przełożonego.
        </p>
      )}

      {rozmowa.length === 0 && przyklady.length > 0 && (
        <div className="przyklady">
          {przyklady.map((p) => (
            <button type="button" key={p} className="jasny" onClick={() => void zapytaj(p)}>
              {p}
            </button>
          ))}
        </div>
      )}

      <ol className="rozmowa" aria-live="polite">
        {rozmowa.map((w, i) => (
          <li key={w.id} ref={i === rozmowa.length - 1 ? ostatnie : undefined}>
            <p className="pytanie">
              {w.pytanie}
              {w.sciezka && <span className="znacznik">{NAZWA_SCIEZKI[w.sciezka]}</span>}
            </p>
            {!w.odpowiedz && !w.blad && <p className="meta">Szukam w źródłach…</p>}
            {w.blad && <p className="blad">{w.blad}</p>}
            {w.odpowiedz && <Odpowiedz o={w.odpowiedz} />}
          </li>
        ))}
      </ol>

      <form onSubmit={wyslij}>
        <textarea
          value={pytanie}
          onChange={(e) => setPytanie(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void zapytaj(pytanie);
            }
          }}
          rows={2}
          placeholder="Zadaj pytanie o zasady oceny, np. „Ile dni ma pracownik na sprzeciw?”"
          aria-label="Pytanie do asystenta formalnego"
        />
        <div className="wiersz">
          {sciezka ? (
            <span className="meta">Ścieżka: {NAZWA_SCIEZKI[sciezka]}</span>
          ) : (
            <div className="wybor" role="group" aria-label="Ścieżka">
              {WYBOR_SCIEZKI.map((s) => (
                <button
                  key={s.wartosc}
                  type="button"
                  aria-pressed={wybrana === s.wartosc}
                  onClick={() => setWybrana(s.wartosc)}
                >
                  {s.nazwa}
                </button>
              ))}
            </div>
          )}
          <button className="jasny" disabled={czekam || !pytanie.trim()}>
            {czekam ? "Szukam…" : "Zapytaj"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Odpowiedz({ o }: { o: OdpowiedzAsystenta }) {
  const [szczegoly, setSzczegoly] = useState(false);
  if (!o.znaleziono) {
    return (
      <div className="brak">
        <strong>Brak wystarczających informacji w bazie wiedzy.</strong>
        {o.nieznane_pojecia.length > 0 && (
          <>
            {" "}
            W materiałach nie znaleziono {o.nieznane_pojecia.length === 1 ? "słowa" : "słów"} z pytania:{" "}
            {o.nieznane_pojecia.map((p) => `„${p}”`).join(", ")}.
          </>
        )}{" "}
        Asystent nie odpowiada bez źródła.
      </div>
    );
  }
  return (
    <div className="odpowiedz">
      {(o.faq_id || o.uproszczona) && o.tresc && <p className="tresc">{o.tresc}</p>}
      {o.cytaty.map((c, i) => (
        <Cytat key={c.fragment_id} c={c} glowny={i === 0} />
      ))}
      {/* Jedno zastrzeżenie na wierzchu; reszta uwag i dane techniczne po rozwinięciu (Karol 22.11: mniej dopisków). */}
      {o.uwagi[0] && <p className="meta">{o.uwagi[0]}</p>}
      <button type="button" className="link" aria-expanded={szczegoly} onClick={() => setSzczegoly((v) => !v)}>
        {szczegoly ? "Ukryj szczegóły" : "Jak powstała odpowiedź"}
      </button>
      {szczegoly && (
        <div className="meta">
          <ul className="uwagi">
            {o.uwagi.slice(1).map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
          <p>
            Tryb: {o.tryb} · dostawca: {o.dostawca}
            {o.faq_id && <> · {o.faq_id}</>}
            {o.odrzuceni.length > 0 && <> · odrzuceni: {o.odrzuceni.join(", ")}</>}
          </p>
        </div>
      )}
    </div>
  );
}

function Cytat({ c, glowny }: { c: CytatAsystenta; glowny: boolean }) {
  const [caly, setCaly] = useState(false);
  const w = c.wyrozniony && c.cytat.includes(c.wyrozniony) ? c.wyrozniony : null;
  const pokaz = caly || !w ? c.cytat : w;
  const kategoria = kategoriaZrodla(c.kategoria);
  return (
    <article className={`cytat ${glowny ? "glowny" : ""}`}>
      <div className="zrodlo">
        <span className={`kategoria ${kategoria.klasa}`}>{kategoria.tekst}</span>
        {c.powoluje_ustawe && (
          <span className="kategoria ustawa" title="Fragment powołuje przepis ustawy; tekst ustawy jest w bazie wiedzy">
            powołuje ustawę
          </span>
        )}
        <strong>{c.dokument}</strong>
        {c.lokalizator && <> · {c.lokalizator}</>}
        {c.strona && c.lokalizator !== `s. ${c.strona}` && <> · s. {c.strona}</>}
      </div>
      <blockquote>
        {caly && w ? <Wyroznij tekst={c.cytat} fraza={w} /> : pokaz}
      </blockquote>
      {w && w !== c.cytat && (
        <button type="button" className="link" onClick={() => setCaly((v) => !v)}>
          {caly ? "Pokaż wyróżnione zdanie" : "Pokaż cały fragment"}
        </button>
      )}
    </article>
  );
}

function Wyroznij({ tekst, fraza }: { tekst: string; fraza: string }) {
  const i = tekst.indexOf(fraza);
  if (i < 0) return <>{tekst}</>;
  return (
    <>
      {tekst.slice(0, i)}
      <mark>{fraza}</mark>
      {tekst.slice(i + fraza.length)}
    </>
  );
}
