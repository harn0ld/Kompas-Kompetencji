import { useEffect, useState } from "react";
import {
  BladApi,
  pobierzArkusz,
  pobierzArkuszPdf,
  zapiszArkusz,
  zarejestrujEzd,
  type ArkuszOkresowy,
  type BrakArkusza,
  type PoleArkusza,
  type Pracownik,
  type ProcesOceny,
} from "./api";
import { opisBledu } from "./Krok1";
import { PoleDaty, poprawnaData, zapiszPlik } from "./Wynik";

const data = (iso: string) => iso.split("-").reverse().join(".");

function bladArkusza(err: unknown): { tekst: string; braki?: BrakArkusza[] } {
  if (err instanceof BladApi) {
    const d = err.detail as { komunikat?: string; braki?: BrakArkusza[] } | string | null;
    if (err.status === 409) return { tekst: "Dane procesu zmieniły się w międzyczasie. Odśwież arkusz (wróć i wejdź ponownie)." };
    if (d && typeof d === "object" && d.komunikat) return { tekst: d.komunikat, braki: d.braki };
  }
  return { tekst: opisBledu(err) };
}

function Wartosc({ p }: { p: PoleArkusza }) {
  if (p.rodzaj === "miejsce_na_podpis_odreczny") return <span className="meta">podpis odręczny na wydruku</span>;
  if (p.wartosc === null || p.wartosc === "") return <span className="meta">—</span>;
  if (p.rodzaj === "data") return <>{data(p.wartosc)}</>;
  if (p.rodzaj === "wybor_punktow") return <>{p.wartosc} pkt</>;
  if (p.rodzaj === "liczba_dziesietna") return <>{p.wartosc.replace(".", ",")}</>;
  return <span className="tekst-pola">{p.wartosc}</span>;
}

function Pole({
  p,
  wartosc,
  brak,
  edycja,
  onZmiana,
}: {
  p: PoleArkusza;
  wartosc: string | null;
  brak?: BrakArkusza;
  edycja: boolean;
  onZmiana: (v: string | null) => void;
}) {
  const przypisy = p.przypisy.length > 0 && <sup className="meta"> {p.przypisy.join(", ")}</sup>;
  // Tekst stały wzoru (oświadczenie, nazwa kryterium) bywa jednocześnie etykietą i wartością: pokazujemy go raz.
  const tenSamTekst = !edycja && (p.wartosc ?? "").trim().toLowerCase() === p.etykieta.trim().toLowerCase();
  if (tenSamTekst) {
    return (
      <div className="pole-arkusza">
        <span className="tekst-pola">{p.wartosc}</span>
        {przypisy}
      </div>
    );
  }
  if (edycja && p.rodzaj === "data") {
    return (
      <div className="pole-arkusza">
        <PoleDaty nazwa={p.etykieta} wartosc={wartosc} onZmiana={onZmiana} />
        {brak && <p className="blad">{brak.komunikat}</p>}
      </div>
    );
  }
  return (
    <div className="pole-arkusza">
      <label className="etykieta">
        <span>
          {p.etykieta}
          {przypisy}
        </span>
        {edycja &&
          (p.rodzaj === "tekst_wielowierszowy" ? (
            <textarea rows={3} value={wartosc ?? ""} aria-invalid={!!brak} onChange={(e) => onZmiana(e.target.value || null)} />
          ) : (
            <input value={wartosc ?? ""} aria-invalid={!!brak} onChange={(e) => onZmiana(e.target.value || null)} />
          ))}
      </label>
      {!edycja && (
        <div>
          <Wartosc p={p} />
        </div>
      )}
      {brak && <p className="blad">{brak.komunikat}</p>}
    </div>
  );
}

export function Arkusz({
  token,
  osoba,
  proces,
  moznaProwadzic,
  onWstecz,
  onDalej,
}: {
  token: string;
  osoba: Pracownik;
  proces: ProcesOceny;
  moznaProwadzic: boolean;
  onWstecz: () => void;
  onDalej: () => void;
}) {
  const [arkusz, setArkusz] = useState<ArkuszOkresowy | null>(null);
  const [pola, setPola] = useState<Record<string, string | null>>({});
  const [braki, setBraki] = useState<BrakArkusza[]>([]);
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  const [zmienione, setZmienione] = useState(false);

  function przyjmij(a: ArkuszOkresowy) {
    setArkusz(a);
    setBraki(a.braki);
    setZmienione(false);
    setPola(Object.fromEntries(a.sekcje.flatMap((s) => s.pola).filter((p) => p.edytowalne).map((p) => [p.id, p.wartosc])));
  }

  useEffect(() => {
    pobierzArkusz(token, proces.id)
      .then(przyjmij)
      .catch((err) => setBlad(bladArkusza(err).tekst));
  }, [token, proces.id]);

  async function wykonaj(czynnosc: () => Promise<void>) {
    setCzekam(true);
    setBlad(null);
    try {
      await czynnosc();
    } catch (err) {
      const b = bladArkusza(err);
      setBlad(b.tekst);
      if (b.braki) setBraki(b.braki);
    } finally {
      setCzekam(false);
    }
  }

  const naglowek = (
    <section>
      <div className="wiersz">
        <div>
          <div className="etykieta">Krok 7 z 8 · Arkusz oceny</div>
          <h2>
            {osoba.imie} {osoba.nazwisko}
          </h2>
          <p className="opis">
            arkusz {proces.arkusz}
            {arkusz && ` · wzór z załącznika nr ${arkusz.zrodlo.zalacznik} (${arkusz.wersja_wzoru})`}
          </p>
        </div>
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do wyniku i terminów
        </button>
      </div>
      {arkusz && <p className="brak">{arkusz.komunikat_podpis} Podpisy składa się odręcznie na wydruku.</p>}
      {arkusz?.zatwierdzony && <p className="sukces">Arkusz zatwierdzony.</p>}
      {blad && <p className="blad">{blad}</p>}
      {!arkusz && !blad && <p className="meta">Wczytuję arkusz…</p>}
    </section>
  );
  if (!arkusz) return naglowek;

  const edycja = moznaProwadzic && !czekam;
  const brakPola = Object.fromEntries(braki.map((b) => [b.id, b]));
  const ogolne = braki.filter((b) => !arkusz.sekcje.some((s) => s.pola.some((p) => p.id === b.id && p.widoczne)));
  const zlaData = arkusz.sekcje
    .flatMap((s) => s.pola)
    .some((p) => p.edytowalne && p.rodzaj === "data" && !poprawnaData(pola[p.id]));
  const ezd = arkusz.rejestracja_ezd;

  return (
    <>
      {naglowek}

      {braki.length > 0 && (
        <section>
          <h2>Braki ({braki.length})</h2>
          <p className="meta">PDF, zatwierdzenie i rejestracja w EZD wymagają kompletnego arkusza.</p>
          <ul className="lista-brakow">
            {braki.map((b) => (
              <li key={b.id}>
                <strong>{b.etykieta}:</strong> {b.komunikat}
              </li>
            ))}
          </ul>
          {ogolne.some((b) => b.id === "wynik_okresowy") && (
            <button type="button" className="jasny" onClick={onWstecz}>
              Przejdź do wyniku i terminów
            </button>
          )}
        </section>
      )}

      {arkusz.sekcje
        .filter((s) => s.widoczna)
        .map((s) => (
          <section key={s.tytul}>
            <h2>{s.tytul}</h2>
            <div className="pola-arkusza">
              {s.pola
                .filter((p) => p.widoczne)
                .map((p) => (
                  <Pole
                    key={p.id}
                    p={p}
                    wartosc={p.edytowalne ? (pola[p.id] ?? null) : p.wartosc}
                    brak={brakPola[p.id]}
                    edycja={edycja && p.edytowalne}
                    onZmiana={(v) => {
                      setZmienione(true);
                      setPola((x) => ({ ...x, [p.id]: v }));
                    }}
                  />
                ))}
            </div>
          </section>
        ))}

      <section>
        <h2>Dokument</h2>
        {zlaData && <p className="blad">Podaj datę w formacie RRRR-MM-DD, np. 2026-11-21.</p>}
        {zmienione && <p className="meta">Masz niezapisane zmiany. PDF i EZD dotyczą ostatniego zapisu.</p>}
        <div className="wiersz">
          <div className="etykiety">
            <button
              type="button"
              className="jasny"
              disabled={!arkusz.pdf_dostepny || czekam}
              onClick={() => wykonaj(async () => zapiszPlik(await pobierzArkuszPdf(token, proces.id), `arkusz-${proces.arkusz}-${osoba.nazwisko}.pdf`))}
            >
              Pobierz PDF
            </button>
            {moznaProwadzic && (
              <button
                type="button"
                className="jasny"
                disabled={!arkusz.pdf_dostepny || czekam || zmienione}
                onClick={() =>
                  wykonaj(async () => {
                    await zarejestrujEzd(token, proces.id);
                    przyjmij(await pobierzArkusz(token, proces.id));
                  })
                }
              >
                Zarejestruj w EZD (próbnie)
              </button>
            )}
          </div>
          {moznaProwadzic && (
            <div className="etykiety">
              <button type="button" className="jasny" disabled={czekam || zlaData} onClick={() => wykonaj(async () => przyjmij(await zapiszArkusz(token, proces.id, pola, false)))}>
                Zapisz szkic
              </button>
              <button type="button" disabled={czekam || zlaData} onClick={() => wykonaj(async () => przyjmij(await zapiszArkusz(token, proces.id, pola, true)))}>
                {czekam ? "Zapisuję…" : "Zatwierdź arkusz"}
              </button>
            </div>
          )}
        </div>
        {ezd && (
          <p className="sukces">
            Zarejestrowano w EZD (próbnie): {ezd.numer_sprawy}, {data(ezd.zarejestrowano.slice(0, 10))}, skrót PDF {ezd.sha256_pdf.slice(0, 12)}…
          </p>
        )}
        <div className="wiersz">
          <span className="meta">Propozycje do pola „Wnioski dotyczące indywidualnego programu rozwoju zawodowego”.</span>
          <button type="button" className="jasny" onClick={onDalej}>
            Dalej: wnioski rozwojowe
          </button>
        </div>
        <details className="pozostale">
          <summary>Przypisy wzoru</summary>
          <ol className="slad">
            {Object.entries(arkusz.przypisy).map(([nr, tekst]) => (
              <li key={nr} value={Number(nr)} className="meta">
                {tekst}
              </li>
            ))}
          </ol>
        </details>
      </section>
    </>
  );
}
