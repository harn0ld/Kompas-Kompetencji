import { FormEvent, useCallback, useEffect, useState } from "react";
import { BladApi, celeApi, type Cel, type Pracownik, type PodpowiedzCelu, type StatusCelu, type TrescCelu } from "./api";
import { Ikona } from "./Ikona";
import type { Sesja } from "./Konto";
import { SzkieletListy } from "./Lista";
import { data } from "./zespol-dane";
import "./cele.css";

/**
 * Cele rozwojowe osoby (#11): lista z jedną czynnością na stan, formularz, podpowiedzi i historia.
 * Ten sam komponent jest na karcie pracownika (``maks`` = 3) i na stronie celów. Akceptację daje
 * przełożony; pracownik proponuje (gdy wolno), rozpoczyna realizację i zgłasza osiągnięcie. HR czyta.
 */
type Strona = "przelozony" | "pracownik" | "odczyt";

const STATUS: Record<StatusCelu, [string, string]> = {
  propozycja: ["do akceptacji", "neutralna"],
  zatwierdzony: ["zatwierdzony", "info"],
  w_realizacji: ["w realizacji", "info"],
  osiągnięty: ["osiągnięty", "pozytywna"],
  odrzucony: ["do poprawy", "uwaga"],
  porzucony: ["porzucony", "wyciszona"],
};
const KOLEJNOSC: StatusCelu[] = ["odrzucony", "propozycja", "w_realizacji", "zatwierdzony", "osiągnięty", "porzucony"];
const POLA: Record<string, string> = {
  nazwa: "nazwa", opis: "opis", miernik: "miernik", termin: "termin", wskaznik_id: "wskaźnik",
  komentarz: "komentarz przełożonego", zgloszono_osiagniecie: "zgłoszenie osiągnięcia",
};
const PUSTY: TrescCelu = { nazwa: "", opis: "", miernik: "", termin: "" };

const naIso = (t: string) => {
  const m = t.trim().match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  return m ? `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}` : null;
};
const opisBledu = (e: unknown) =>
  e instanceof BladApi && typeof e.detail === "string" ? e.detail : "Nie udało się zapisać. Spróbuj jeszcze raz.";
const wymagaDzialania = (c: Cel, s: Strona) =>
  s === "przelozony" ? c.status === "propozycja" || !!c.zgloszono_osiagniecie : c.status === "odrzucony";

function Formularz({
  poczatek,
  przycisk,
  onZapisz,
  onAnuluj,
}: {
  poczatek: TrescCelu;
  przycisk: string;
  onZapisz: (t: TrescCelu) => Promise<void>;
  onAnuluj: () => void;
}) {
  const [t, setT] = useState({ ...poczatek, termin: poczatek.termin ? data(poczatek.termin) : "" });
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  const pole = (k: keyof TrescCelu) => ({
    value: (t[k] as string) ?? "",
    onChange: (e: { target: { value: string } }) => setT((x) => ({ ...x, [k]: e.target.value })),
  });

  async function zapisz(e: FormEvent) {
    e.preventDefault();
    const termin = t.termin?.trim() ? naIso(t.termin) : null;
    if (t.termin?.trim() && !termin) return setBlad("Termin wpisz jako dd.mm.rrrr, np. 30.06.2027.");
    setCzekam(true);
    setBlad(null);
    try {
      await onZapisz({ ...t, nazwa: t.nazwa.trim(), opis: t.opis || null, miernik: t.miernik || null, termin });
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setCzekam(false);
    }
  }

  return (
    <form className="cel-formularz" onSubmit={zapisz}>
      <label>
        Cel
        <input required maxLength={200} placeholder="np. Prowadzenie spotkań zespołu" {...pole("nazwa")} />
      </label>
      <label>
        Miernik
        <input maxLength={500} placeholder="np. 3 spotkania z notatką" {...pole("miernik")} />
      </label>
      <label>
        Termin
        <input inputMode="numeric" placeholder="dd.mm.rrrr" {...pole("termin")} />
      </label>
      <label className="szeroko">
        Opis
        <textarea rows={3} maxLength={2000} {...pole("opis")} />
      </label>
      {blad && <p className="blad szeroko">{blad}</p>}
      <div className="cel-akcje szeroko">
        <button disabled={czekam || !t.nazwa.trim()}>{czekam ? "Zapisuję…" : przycisk}</button>
        <button type="button" className="link" onClick={onAnuluj}>
          Anuluj
        </button>
      </div>
    </form>
  );
}

function Historia({ cel }: { cel: Cel }) {
  return (
    <ol className="cel-historia">
      {[...cel.historia].reverse().map((w, i) => {
        const pola = Object.keys(w.zmiany);
        const nowy = pola.every((p) => w.zmiany[p].przed == null);
        const st = w.zmiany.status;
        const tresc = pola.filter((p) => p !== "status").map((p) => POLA[p] ?? p);
        const opis = nowy
          ? "dodanie celu"
          : [
              st && `${STATUS[st.przed as StatusCelu]?.[0] ?? st.przed} → ${STATUS[st.po as StatusCelu]?.[0] ?? st.po}`,
              tresc.length > 0 && `zmiana: ${tresc.join(", ")}`,
            ]
              .filter(Boolean)
              .join(" · ");
        return (
          <li key={i}>
            {data(w.czas)} · {w.autor} · {opis}
          </li>
        );
      })}
    </ol>
  );
}

function WierszCelu({
  cel,
  strona,
  edycja,
  otwarty,
  onPrzelacz,
  onZmiana,
  token,
}: {
  cel: Cel;
  strona: Strona;
  edycja: boolean;
  otwarty: boolean;
  onPrzelacz: () => void;
  onZmiana: (c: Cel) => void;
  token: string;
}) {
  const [tryb, setTryb] = useState<"lista" | "edycja" | "odrzucenie" | "porzucenie">("lista");
  const [komentarz, setKomentarz] = useState("");
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  const [etykieta, ton] = STATUS[cel.status];
  const koncowy = cel.status === "osiągnięty" || cel.status === "porzucony";
  const przel = strona === "przelozony";
  const prac = strona === "pracownik";

  async function wykonaj(akcja: () => Promise<Cel>) {
    setCzekam(true);
    setBlad(null);
    try {
      onZmiana(await akcja());
      setTryb("lista");
      setKomentarz("");
    } catch (e) {
      setBlad(opisBledu(e));
    } finally {
      setCzekam(false);
    }
  }

  // Jedna czynność główna na stan; pozostałe jako łącza.
  let glowna: [string, () => Promise<Cel>] | null = null;
  if (przel && cel.status === "propozycja") glowna = ["Zatwierdź", () => celeApi.zatwierdz(token, cel.id)];
  else if (przel && cel.zgloszono_osiagniecie && !koncowy)
    glowna = ["Potwierdź osiągnięcie", () => celeApi.status(token, cel.id, "osiągnięty")];
  else if (cel.status === "zatwierdzony" && (przel || prac))
    glowna = ["Rozpocznij realizację", () => celeApi.status(token, cel.id, "w_realizacji")];
  else if (prac && cel.status === "w_realizacji" && !cel.zgloszono_osiagniecie)
    glowna = ["Zgłoś osiągnięcie", () => celeApi.status(token, cel.id, "osiągnięty")];
  const moznaEdytowac = !koncowy && (przel || (prac && edycja));

  return (
    <div className={`cel ${otwarty ? "otwarty" : ""}`}>
      <button type="button" className="cel-glowa" aria-expanded={otwarty} onClick={onPrzelacz}>
        <span className="cel-nazwa">
          {cel.nazwa}
          <span className={`status ${ton}`}>{etykieta}</span>
          {cel.zgloszono_osiagniecie && !koncowy && <span className="status uwaga">zgłoszono osiągnięcie</span>}
        </span>
        <span className="cel-opis">
          {[cel.miernik, cel.termin && `do ${data(cel.termin)}`].filter(Boolean).join(" · ") || "bez miernika i terminu"}
        </span>
        <Ikona nazwa={otwarty ? "gora" : "dalej"} />
      </button>
      {otwarty && (
        <div className="cel-cialo">
          {tryb === "edycja" ? (
            <Formularz
              poczatek={cel}
              przycisk={prac ? "Wyślij do akceptacji" : "Zapisz zmiany"}
              onZapisz={(t) => wykonaj(() => celeApi.zmien(token, cel.id, t))}
              onAnuluj={() => setTryb("lista")}
            />
          ) : (
            <>
              {cel.opis && <p>{cel.opis}</p>}
              {cel.komentarz && (
                <p className="cel-komentarz">
                  <strong>Komentarz przełożonego:</strong> {cel.komentarz}
                </p>
              )}
              {tryb === "odrzucenie" && (
                <div className="cel-odrzucenie">
                  <label>
                    Co poprawić?
                    <textarea rows={2} maxLength={2000} value={komentarz} onChange={(e) => setKomentarz(e.target.value)} />
                  </label>
                  <div className="cel-akcje">
                    <button
                      disabled={czekam || !komentarz.trim()}
                      onClick={() => wykonaj(() => celeApi.odrzuc(token, cel.id, komentarz.trim()))}
                    >
                      Odeślij do poprawy
                    </button>
                    <button type="button" className="link" onClick={() => setTryb("lista")}>
                      Anuluj
                    </button>
                  </div>
                </div>
              )}
              {tryb === "porzucenie" && (
                <div className="cel-akcje">
                  <span>Porzucony cel zostaje w historii i nie można go już zmienić.</span>
                  <button disabled={czekam} onClick={() => wykonaj(() => celeApi.status(token, cel.id, "porzucony"))}>
                    Porzuć cel
                  </button>
                  <button type="button" className="link" onClick={() => setTryb("lista")}>
                    Anuluj
                  </button>
                </div>
              )}
              {tryb === "lista" && (glowna || moznaEdytowac || (przel && !koncowy)) && (
                <div className="cel-akcje">
                  {glowna && (
                    <button disabled={czekam} onClick={() => wykonaj(glowna![1])}>
                      {glowna[0]}
                    </button>
                  )}
                  {przel && cel.status === "propozycja" && (
                    <button type="button" className="link" onClick={() => setTryb("odrzucenie")}>
                      Odeślij do poprawy
                    </button>
                  )}
                  {moznaEdytowac && (
                    <button type="button" className="link" onClick={() => setTryb("edycja")}>
                      {prac && cel.status === "odrzucony" ? "Popraw" : "Edytuj"}
                    </button>
                  )}
                  {przel && !koncowy && (
                    <button type="button" className="link" onClick={() => setTryb("porzucenie")}>
                      Porzuć
                    </button>
                  )}
                </div>
              )}
              {blad && <p className="blad">{blad}</p>}
              <Historia cel={cel} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function CeleOsoby({
  sesja,
  osoba,
  maks,
  tytul = "Cele rozwojowe",
}: {
  sesja: Sesja;
  osoba: Pracownik;
  /** Ile celów pokazać od razu (na karcie 3); reszta pod „Pokaż wszystkie”. */
  maks?: number;
  tytul?: string;
}) {
  const rola = sesja.uzytkownik.rola;
  const strona: Strona = rola === "przelozony" ? "przelozony" : rola === "oceniany" ? "pracownik" : "odczyt";
  const [cele, setCele] = useState<Cel[] | null>(null);
  const [edycja, setEdycja] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);
  const [otwarty, setOtwarty] = useState<number | null>(null);
  const [nowy, setNowy] = useState<TrescCelu | null>(null);
  const [podpowiedzi, setPodpowiedzi] = useState<{ komunikat: string | null; lista: PodpowiedzCelu[] } | null>(null);
  const [wszystkie, setWszystkie] = useState(false);

  const wczytaj = useCallback(() => {
    Promise.all([celeApi.lista(sesja.token, osoba.osoba_id), celeApi.ustawienia(sesja.token)])
      .then(([c, u]) => {
        setCele(c);
        setEdycja(u.pracownik_moze_edytowac);
      })
      .catch(() => setBlad("Nie udało się pobrać celów."));
  }, [sesja.token, osoba.osoba_id]);
  useEffect(wczytaj, [wczytaj]);

  const moznaDodac = strona === "przelozony" || (strona === "pracownik" && edycja);
  const podmien = (c: Cel) => setCele((x) => x?.map((y) => (y.id === c.id ? c : y)) ?? null);

  async function dodaj(t: TrescCelu) {
    const c = await celeApi.dodaj(sesja.token, osoba.osoba_id, t);
    setCele((x) => [...(x ?? []), c]);
    setNowy(null);
    setOtwarty(c.id);
  }

  async function pokazPodpowiedzi() {
    try {
      const p = await celeApi.podpowiedzi(sesja.token, osoba.osoba_id);
      setPodpowiedzi({ komunikat: p.komunikat, lista: p.podpowiedzi });
    } catch {
      setPodpowiedzi({ komunikat: "Nie udało się pobrać podpowiedzi.", lista: [] });
    }
  }

  const posortowane = [...(cele ?? [])].sort(
    (a, b) =>
      Number(wymagaDzialania(b, strona)) - Number(wymagaDzialania(a, strona)) ||
      KOLEJNOSC.indexOf(a.status) - KOLEJNOSC.indexOf(b.status),
  );
  const widoczne = maks && !wszystkie ? posortowane.slice(0, maks) : posortowane;
  const doDzialania = posortowane.filter((c) => wymagaDzialania(c, strona)).length;

  return (
    <section className="cele">
      <div className="wiersz-tytulu">
        <h2>
          {tytul}{" "}
          {doDzialania > 0 && <span className="status uwaga">{strona === "przelozony" ? `${doDzialania} do decyzji` : `${doDzialania} do poprawy`}</span>}
        </h2>
        {moznaDodac && !nowy && (
          <div className="cele-naglowek-akcje">
            <button type="button" className="link" onClick={pokazPodpowiedzi}>
              Zaproponuj cele
            </button>
            <button type="button" className="jasny" onClick={() => setNowy(PUSTY)}>
              <Ikona nazwa="plus" /> Dodaj cel
            </button>
          </div>
        )}
      </div>
      {strona === "pracownik" && !edycja && (
        <p className="meta">Cele ustala przełożony. Możesz rozpocząć ich realizację i zgłosić osiągnięcie.</p>
      )}

      {podpowiedzi && (
        <div className="cele-podpowiedzi">
          <div className="wiersz-tytulu">
            <strong>Podpowiedzi z ostatniej oceny</strong>
            <button type="button" className="link" onClick={() => setPodpowiedzi(null)}>
              Zamknij
            </button>
          </div>
          {podpowiedzi.komunikat && <p className="meta">{podpowiedzi.komunikat}</p>}
          {podpowiedzi.lista.map((p) => (
            <div key={p.wskaznik_id ?? p.nazwa} className="cele-podpowiedz">
              <span className="meta">{p.podstawa}</span>
              <span>{p.opis}</span>
              <button
                type="button"
                className="jasny"
                onClick={() => {
                  setNowy({ nazwa: p.nazwa.slice(0, 200), opis: p.opis, wskaznik_id: p.wskaznik_id, miernik: "", termin: "" });
                  setPodpowiedzi(null);
                }}
              >
                {strona === "przelozony" ? "Dodaj jako cel" : "Dodaj jako propozycję"}
              </button>
            </div>
          ))}
        </div>
      )}

      {nowy && (
        <Formularz
          poczatek={nowy}
          przycisk={strona === "przelozony" ? "Dodaj cel" : "Wyślij do akceptacji"}
          onZapisz={dodaj}
          onAnuluj={() => setNowy(null)}
        />
      )}

      {blad && <p className="blad">{blad}</p>}
      {!blad && cele === null && <SzkieletListy wiersze={2} />}
      {cele?.length === 0 && !nowy && <p className="meta">Nie ma jeszcze celów.</p>}
      <div className="lista">
        {widoczne.map((c) => (
          <WierszCelu
            key={c.id}
            cel={c}
            strona={strona}
            edycja={edycja}
            otwarty={otwarty === c.id}
            onPrzelacz={() => setOtwarty((o) => (o === c.id ? null : c.id))}
            onZmiana={podmien}
            token={sesja.token}
          />
        ))}
      </div>
      {maks && posortowane.length > maks && (
        <button type="button" className="link cele-wiecej" onClick={() => setWszystkie((v) => !v)}>
          {wszystkie ? "Pokaż mniej" : `Pokaż wszystkie (${posortowane.length})`}
        </button>
      )}
    </section>
  );
}
