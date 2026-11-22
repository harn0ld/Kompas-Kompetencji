import { type FormEvent, useState } from "react";
import { pytajWczacieRozmowy, type OdpowiedzCzatuRozmowy } from "./api";
import { opisBledu } from "./Krok1";

/* Asystent rozmowy (#7): czat przełożonego z RAG na materiałach i pseudonimizowanym kontekstem oceny.
   Rozmowa oceniająca jest częścią przebiegu „Rozmowa oceniająca” (Ocena.tsx), nie osobnym krokiem. */

interface WymianaCzatu {
  id: number;
  pytanie: string;
  odpowiedz?: OdpowiedzCzatuRozmowy;
  blad?: string;
}

/** `poczatkowe`: pytanie wpisane w pole na start (np. przy wskaźniku); przełożony może je zmienić przed wysłaniem. */
export function CzatRozmowy({ token, procesId, poczatkowe = "" }: { token: string; procesId: number; poczatkowe?: string }) {
  const [pytanie, setPytanie] = useState(poczatkowe);
  const [historia, setHistoria] = useState<WymianaCzatu[]>([]);
  const [czekam, setCzekam] = useState(false);

  async function wyslij(e: FormEvent) {
    e.preventDefault();
    const tekst = pytanie.trim();
    if (!tekst || czekam) return;
    const id = Date.now();
    setHistoria((h) => [...h, { id, pytanie: tekst }]);
    setPytanie("");
    setCzekam(true);
    try {
      const odpowiedz = await pytajWczacieRozmowy(token, procesId, tekst);
      setHistoria((h) => h.map((w) => (w.id === id ? { ...w, odpowiedz } : w)));
    } catch (err) {
      setHistoria((h) => h.map((w) => (w.id === id ? { ...w, blad: opisBledu(err) } : w)));
    } finally {
      setCzekam(false);
    }
  }

  return (
    <div className="czat">
      <p className="opis">
        Asystent korzysta z materiałów oraz pseudonimizowanego kontekstu tej oceny. Nie podejmuje decyzji za przełożonego.
      </p>
      <ol className="rozmowa" aria-live="polite">
        {historia.map((w) => (
          <li key={w.id}>
            <p className="pytanie">{w.pytanie}</p>
            {!w.odpowiedz && !w.blad && <p className="meta">Szukam w źródłach…</p>}
            {w.blad && <p className="blad">{w.blad}</p>}
            {w.odpowiedz && <OdpowiedzCzatu odpowiedz={w.odpowiedz} />}
          </li>
        ))}
      </ol>
      <form onSubmit={wyslij}>
        <textarea
          rows={2}
          aria-label="Pytanie do asystenta rozmowy"
          placeholder="Np. jak przekazać ocenę 3 za współpracę?"
          value={pytanie}
          onChange={(e) => setPytanie(e.target.value)}
        />
        <div className="wiersz">
          <span className="meta">Historia pozostaje w tej sesji.</span>
          <button className="jasny" disabled={czekam || !pytanie.trim()}>
            {czekam ? "Szukam…" : "Zapytaj"}
          </button>
        </div>
      </form>
    </div>
  );
}

function OdpowiedzCzatu({ odpowiedz }: { odpowiedz: OdpowiedzCzatuRozmowy }) {
  if (!odpowiedz.znaleziono) {
    return <p className="brak">{odpowiedz.komunikat} Asystent nie odpowiada bez źródła.</p>;
  }
  return (
    <div className="odpowiedz">
      {odpowiedz.cytaty.length > 0 && <p className="brak">{odpowiedz.oznaczenie_sugestii}</p>}
      {odpowiedz.tresc && <p>{odpowiedz.tresc}</p>}
      {/* Zgłoszenie 178: przygotowanie do rozmowy – dwie krótkie listy, każdy punkt oparty na cytowanym fragmencie niżej. */}
      {!!odpowiedz.kwestie?.length && (
        <div className="punkty-przygotowania">
          <span className="kafel-etykieta">Do omówienia</span>
          <ul>
            {odpowiedz.kwestie.map((k) => (
              <li key={k}>{k}</li>
            ))}
          </ul>
        </div>
      )}
      {!!odpowiedz.argumenty?.length && (
        <div className="punkty-przygotowania">
          <span className="kafel-etykieta">Argumenty z przebiegu oceny</span>
          <ul>
            {odpowiedz.argumenty.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
      {/* Karol 22.11 09:16: krótka odpowiedź, a pod nią źródła z możliwością rozwinięcia. Bez listy punktów
          (stara ścieżka) cytaty są odpowiedzią, więc zostają rozwinięte. */}
      {odpowiedz.cytaty.length > 0 && (
      <details className="zrodla-odpowiedzi" open={!(odpowiedz.kwestie?.length || odpowiedz.argumenty?.length)}>
        <summary>Źródła ({odpowiedz.cytaty.length})</summary>
        {odpowiedz.cytaty.map((cytat) => (
          <article className="cytat" key={cytat.fragment_id}>
            <div className="zrodlo">
              <strong>{cytat.dokument}</strong>
              {cytat.lokalizator && <> · {cytat.lokalizator}</>}
              {cytat.strona && <> · s. {cytat.strona}</>}
            </div>
            <blockquote>{cytat.wyrozniony || cytat.cytat}</blockquote>
          </article>
        ))}
      </details>
      )}
      {odpowiedz.tryb && (
        <p className="meta">
          Tryb: {odpowiedz.tryb} · dostawca: {odpowiedz.dostawca}
        </p>
      )}
    </div>
  );
}
