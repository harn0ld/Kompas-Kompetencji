import { useEffect, useState } from "react";
import {
  BladApi,
  pobierzArkusz,
  pobierzWnioski,
  zapiszArkusz,
  type PropozycjaRozwoju,
  type Pracownik,
  type ProcesOceny,
  type SourceRef,
  type WnioskiProcesu,
} from "./api";
import { Zrodla, opisBledu } from "./Krok1";

function Propozycja({ p }: { p: PropozycjaRozwoju }) {
  return (
    <li className="kryterium">
      <strong>{p.wskaznik}</strong>
      <p className="meta">
        {p.kompetencja}
        {p.poziom !== null && ` · poziom ${p.poziom}`}
      </p>
      {p.przyklady.map((x) => (
        <p key={x}>
          <span className="etykieta">Przykład:</span> {x}
        </p>
      ))}
      <div className="etykiety">
        {p.formy.map((f) => (
          <span key={f.id} className="znacznik">
            {f.nazwa}
          </span>
        ))}
      </div>
      {p.uwagi.map((u) => (
        <p key={u} className="brak">
          {u}
        </p>
      ))}
    </li>
  );
}

export function Wnioski({
  token,
  osoba,
  proces,
  moznaProwadzic,
  onWstecz,
}: {
  token: string;
  osoba: Pracownik;
  proces: ProcesOceny;
  moznaProwadzic: boolean;
  onWstecz: () => void;
}) {
  const [dane, setDane] = useState<WnioskiProcesu | null>(null);
  const [tresc, setTresc] = useState("");
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  const [zapisano, setZapisano] = useState<string | null>(null);

  useEffect(() => {
    if (!moznaProwadzic) return;
    pobierzWnioski(token, proces.id)
      .then((d) => {
        setDane(d);
        setTresc(d.wnioski_w_arkuszu ?? "");
      })
      .catch((err) => setBlad(opisBledu(err)));
  }, [token, proces.id, moznaProwadzic]);

  async function zapisz() {
    if (!dane?.pole_arkusza) return;
    setCzekam(true);
    setBlad(null);
    setZapisano(null);
    try {
      // Wnioski są polem arkusza z kroku 7: zapis idzie przez arkusz, który zastępuje cały zestaw uzupełnień.
      const arkusz = await pobierzArkusz(token, proces.id);
      const pola = Object.fromEntries(
        arkusz.sekcje.flatMap((s) => s.pola).filter((p) => p.edytowalne).map((p) => [p.id, p.wartosc]),
      );
      pola[dane.pole_arkusza] = tresc.trim() || null;
      const po = await zapiszArkusz(token, proces.id, pola, false);
      setZapisano(
        arkusz.zatwierdzony && !po.zatwierdzony
          ? "Zapisano w arkuszu. Zmiana cofnęła zatwierdzenie i rejestrację w EZD: zatwierdź arkusz ponownie w kroku 7."
          : "Zapisano w arkuszu.",
      );
      setDane(await pobierzWnioski(token, proces.id));
    } catch (err) {
      const d = err instanceof BladApi ? (err.detail as { komunikat?: string } | null) : null;
      setBlad(d?.komunikat ?? opisBledu(err));
    } finally {
      setCzekam(false);
    }
  }

  const naglowek = (
    <section>
      <div className="wiersz">
        <div>
          <div className="etykieta">Krok 8 z 8 · Wnioski rozwojowe</div>
          <h2>
            {osoba.imie} {osoba.nazwisko}
          </h2>
          <p className="opis">
            {proces.sciezka === "okresowa" ? "ocena okresowa" : "pierwsza ocena"}
            {dane && ` · wynik oceny: ${dane.wynik_oceny ?? "jeszcze nie ma (krok 5 niekompletny)"}`}
          </p>
        </div>
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do arkusza
        </button>
      </div>
      {!moznaProwadzic && <p className="brak">Propozycje rozwoju przygotowuje i widzi tylko przełożony. Wnioski są w arkuszu (krok 7).</p>}
      {dane && (
        <p className="brak">
          {dane.propozycje.status}. Asystent niczego nie wpisuje: treść wniosków pisze przełożony.
        </p>
      )}
      {blad && <p className="blad">{blad}</p>}
      {moznaProwadzic && !dane && !blad && <p className="meta">Wczytuję propozycje…</p>}
    </section>
  );
  if (!dane) return naglowek;

  const pr = dane.propozycje;
  const obszary = pr.propozycje.filter((p) => p.typ === "OBSZAR_ROZWOJOWY");
  const mocne = pr.propozycje.filter((p) => p.typ === "MOCNA_STRONA");
  const formy = new Map<string, { nazwa: string; adnotacje: SourceRef[] }>();
  pr.propozycje.forEach((p) => p.formy.forEach((f) => formy.set(f.id, f)));

  return (
    <>
      {naglowek}

      {!pr.dostepne && pr.komunikat && (
        <section>
          <p className="brak">{pr.komunikat}</p>
        </section>
      )}

      {pr.dostepne && (
        <section>
          <h2>Propozycje z kroków 3–5</h2>
          {pr.propozycje.length === 0 && (
            <p className="meta">Wszystkie ocenione wskaźniki są na poziomie oczekiwań, więc asystent nie ma propozycji. Wnioski pisze przełożony.</p>
          )}
          {obszary.length > 0 && (
            <>
              <div className="etykieta">Obszary rozwojowe ({obszary.length})</div>
              <ul className="wskazniki">
                {obszary.map((p) => (
                  <Propozycja key={(p.wskaznik_id ?? p.wskaznik) + p.typ} p={p} />
                ))}
              </ul>
            </>
          )}
          {mocne.length > 0 && (
            <>
              <div className="etykieta">Mocne strony ({mocne.length})</div>
              <ul className="wskazniki">
                {mocne.map((p) => (
                  <Propozycja key={(p.wskaznik_id ?? p.wskaznik) + p.typ} p={p} />
                ))}
              </ul>
            </>
          )}
          {pr.pominiete.length > 0 && (
            <p className="meta">
              Pominięte: {pr.pominiete.map((x) => `${x.wskaznik} (${x.powod})`).join("; ")}.
            </p>
          )}
        </section>
      )}

      <section>
        <h2>Wnioski do indywidualnego programu rozwoju</h2>
        <p className="meta">{dane.gdzie_wpisac}</p>
        {dane.pole_arkusza ? (
          <fieldset className="formularz" disabled={czekam}>
            <label className="etykieta">
              Treść wniosków (pisze przełożony)
              <textarea
                rows={5}
                value={tresc}
                placeholder={pr.struktura_wnioskow.join("\n")}
                onChange={(e) => {
                  setTresc(e.target.value);
                  setZapisano(null);
                }}
              />
            </label>
            <div className="wiersz">
              <span className="meta">Zapis do arkusza cofa jego zatwierdzenie, jeśli było.</span>
              <button type="button" disabled={czekam || tresc.trim() === (dane.wnioski_w_arkuszu ?? "")} onClick={zapisz}>
                {czekam ? "Zapisuję…" : "Zapisz wnioski w arkuszu"}
              </button>
            </div>
          </fieldset>
        ) : (
          <p className="brak">Arkusza tej ścieżki jeszcze nie ma, więc wniosków nie da się zapisać.</p>
        )}
        {zapisano && <p className="sukces">{zapisano}</p>}
        {zapisano && (
          <button type="button" className="jasny" onClick={onWstecz}>
            Wróć do arkusza (krok 7)
          </button>
        )}
      </section>

      <section>
        <h2>Zasady propozycji</h2>
        <ul className="zadania">
          {pr.reguly.map((r) => (
            <li key={r.id}>
              {r.opis}
              <Zrodla adnotacje={r.adnotacje} />
            </li>
          ))}
        </ul>
        {formy.size > 0 && (
          <details className="pozostale">
            <summary>Skąd formy rozwoju ({pr.wersja_metodyki})</summary>
            <ul className="zadania">
              {[...formy.entries()].map(([id, f]) => (
                <li key={id}>
                  {f.nazwa}
                  <Zrodla adnotacje={f.adnotacje} />
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>
    </>
  );
}
