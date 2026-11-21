import { useCallback, useEffect, useState } from "react";
import {
  pobierzPracownikow,
  pobierzProcesyHr,
  pobierzPropozycjePrzypomnien,
  pobierzSkrzynke,
  wyslijPrzypomnienie,
  type ProcesHr,
  type PropozycjaPrzypomnienia,
  type Przypomnienie,
} from "./api";
import { NAZWA_SCIEZKI, opisBledu } from "./Krok1";
import { Wybor } from "./Ocena";

const data = (iso: string) => iso.slice(0, 10).split("-").reverse().join(".");

function dni(p: ProcesHr): string {
  if (p.dni_do_terminu === null) return "—";
  if (p.dni_do_terminu < 0) return `${-p.dni_do_terminu} dni po terminie`;
  if (p.dni_do_terminu === 0) return "dziś";
  return `za ${p.dni_do_terminu} dni`;
}

/** Panel HR (#38): statusy i terminy procesów, przypomnienia do przełożonych. Bez treści ocen i notatek. */
export default function PanelHR({ token }: { token: string }) {
  const [zagrozone, setZagrozone] = useState(false);
  const [procesy, setProcesy] = useState<ProcesHr[] | null>(null);
  const [propozycje, setPropozycje] = useState<PropozycjaPrzypomnienia[]>([]);
  const [tresci, setTresci] = useState<Record<number, string>>({});
  const [skrzynka, setSkrzynka] = useState<Przypomnienie[]>([]);
  const [osoby, setOsoby] = useState<Record<string, string>>({});
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState<number | null>(null);

  const odswiezSkrzynke = useCallback(() => pobierzSkrzynke(token).then(setSkrzynka), [token]);

  useEffect(() => {
    pobierzProcesyHr(token, zagrozone)
      .then(setProcesy)
      .catch((err) => setBlad(opisBledu(err)));
  }, [token, zagrozone]);

  useEffect(() => {
    Promise.all([
      pobierzPropozycjePrzypomnien(token).then((p) => {
        setPropozycje(p);
        setTresci(Object.fromEntries(p.map((x) => [x.proces_id, x.tresc])));
      }),
      odswiezSkrzynke(),
      pobierzPracownikow(token).then((l) => setOsoby(Object.fromEntries(l.map((o) => [o.osoba_id, `${o.imie} ${o.nazwisko}`])))),
    ]).catch((err) => setBlad(opisBledu(err)));
  }, [token, odswiezSkrzynke]);

  async function wyslij(p: PropozycjaPrzypomnienia) {
    setCzekam(p.proces_id);
    setBlad(null);
    try {
      await wyslijPrzypomnienie(token, { proces_id: p.proces_id, adresat: p.adresat, tresc: (tresci[p.proces_id] ?? "").trim() });
      await odswiezSkrzynke();
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setCzekam(null);
    }
  }

  const nazwaProcesu = (id: number) => procesy?.find((p) => p.proces_id === id)?.osoba ?? `proces ${id}`;
  const ostatnie = (id: number) => skrzynka.filter((s) => s.proces_id === id).at(-1);

  return (
    <>
      <section>
        <div className="wiersz">
          <h2>Procesy oceny</h2>
          <Wybor
            etykieta="Filtr procesów"
            opcje={[
              { wartosc: "wszystkie", tekst: "wszystkie" },
              { wartosc: "zagrozone", tekst: "zagrożone terminem (7 dni)" },
            ]}
            wartosc={zagrozone ? "zagrozone" : "wszystkie"}
            zablokowane={false}
            onWybierz={(w) => setZagrozone(w === "zagrozone")}
          />
        </div>
        <p className="meta">Panel pokazuje statusy i terminy. Treści ocen ani notatek HR nie widzi.</p>
        {blad && <p className="blad">{blad}</p>}
        {procesy === null && !blad && <p className="meta">Wczytuję procesy…</p>}
        {procesy?.length === 0 && <p className="brak">{zagrozone ? "Żaden proces nie ma terminu w ciągu 7 dni." : "Brak procesów oceny."}</p>}
        {procesy && procesy.length > 0 && (
          <table className="pracownicy">
            <thead>
              <tr>
                <th>Osoba</th>
                <th>Ścieżka</th>
                <th>Krok</th>
                <th>Najbliższy termin</th>
                <th>Stan</th>
              </tr>
            </thead>
            <tbody>
              {procesy.map((p) => (
                <tr key={p.proces_id}>
                  <td className="osoba">
                    {p.osoba}
                    <div className="meta">
                      {p.stanowisko} · przełożony: {osoby[p.przelozony_id] ?? p.przelozony_id}
                    </div>
                  </td>
                  <td>
                    {NAZWA_SCIEZKI[p.sciezka]}
                    <div className="meta">arkusz {p.arkusz === "PIERWSZA" ? "pierwszej oceny" : p.arkusz}</div>
                  </td>
                  <td>{p.krok} z 8</td>
                  <td>
                    {p.najblizszy_termin ? (
                      <>
                        {data(p.najblizszy_termin.data)}
                        <div className="meta">
                          {p.najblizszy_termin.nazwa} · {dni(p)}
                        </div>
                      </>
                    ) : (
                      <span className="meta">{p.komunikat ?? "—"}</span>
                    )}
                  </td>
                  <td>
                    {p.zagrozony ? (
                      <span className="status negatywna">zagrożony</span>
                    ) : (
                      <span className="meta">{p.status === "W_TOKU" ? "w toku" : p.status.toLowerCase()}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2>Przypomnienia do wysłania</h2>
        {propozycje.length === 0 && <p className="meta">Brak terminów, które wymagają przypomnienia.</p>}
        <ul className="wskazniki">
          {propozycje.map((p) => {
            const wyslane = ostatnie(p.proces_id);
            return (
              <li key={p.proces_id} className="kryterium">
                <strong>{nazwaProcesu(p.proces_id)}</strong>
                <p className="meta">
                  Do: {osoby[p.adresat] ?? p.adresat} (przełożony) · termin {data(p.termin.data)}, {p.termin.nazwa}
                </p>
                <label className="etykieta">
                  Treść przypomnienia
                  <textarea rows={2} value={tresci[p.proces_id] ?? ""} onChange={(e) => setTresci((t) => ({ ...t, [p.proces_id]: e.target.value }))} />
                </label>
                <div className="wiersz">
                  <span className="meta">{wyslane ? `Ostatnio wysłano ${data(wyslane.wyslano)}.` : "Jeszcze nie wysłano."}</span>
                  <button
                    type="button"
                    className="jasny"
                    disabled={czekam === p.proces_id || !(tresci[p.proces_id] ?? "").trim()}
                    onClick={() => wyslij(p)}
                  >
                    {czekam === p.proces_id ? "Wysyłam…" : "Wyślij przypomnienie"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <h2>Skrzynka nadawcza (próbna)</h2>
        <p className="meta">Przypomnienia zapisują się tutaj i w historii procesu. Nic nie wychodzi poza aplikację.</p>
        {skrzynka.length === 0 ? (
          <p className="meta">Skrzynka jest pusta.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Wysłano</th>
                <th>Do</th>
                <th>Proces</th>
                <th>Treść</th>
              </tr>
            </thead>
            <tbody>
              {[...skrzynka].reverse().map((s) => (
                <tr key={s.id}>
                  <td>{data(s.wyslano)}</td>
                  <td>{osoby[s.adresat] ?? s.adresat}</td>
                  <td>{nazwaProcesu(s.proces_id)}</td>
                  <td className="meta">{s.tresc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
