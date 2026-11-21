import type { ReactNode } from "react";
import type { Rola, Sciezka } from "./api";
import { Ikona, type NazwaIkony } from "./Ikona";
import type { Sesja } from "./Konto";
import { OknoAsystenta } from "./OknoAsystenta";
import znak from "./wydra/wydra-stoi.webp";

/**
 * Powłoka wersji MC w stylu mObywatela: menu boczne z wydrą jako znakiem, treść i okno asystenta
 * formalnego na środku ekranu; na telefonie menu jest dolnym paskiem.
 */
export type Widok = "pulpit" | "zespol" | "pracownicy" | "cele" | "procesy" | "zrodla";

const NAZWA_ROLI: Record<Rola, string> = { przelozony: "przełożony", hr: "HR / administrator", oceniany: "oceniany" };

interface Props {
  sesja: Sesja;
  widok: Widok | null;
  onWidok: (w: Widok) => void;
  onWyloguj: () => void;
  asystent: boolean;
  onAsystent: (otwarty: boolean) => void;
  /** Ścieżka bieżącego procesu: asystent szuka wtedy tylko w jej rozporządzeniu (#37). */
  sciezka?: Sciezka;
  /** Pytanie przekazane z pulpitu; zmiana `id` wysyła je do asystenta. */
  pytanie?: { id: number; tekst: string } | null;
  children: ReactNode;
}

export function Powloka({ sesja, widok, onWidok, onWyloguj, asystent, onAsystent, sciezka, pytanie, children }: Props) {
  const { login, rola } = sesja.uzytkownik;
  const pozycje: [Widok, NazwaIkony, string][] = [
    ["pulpit", "dom", "Pulpit"],
    // Zespół (działy, liczby, wykresy) zastępuje płaską listę pracowników; oceniany widzi swoje dane.
    rola === "oceniany" ? ["pracownicy", "osoby", "Twoje dane"] : ["zespol", "osoby", "Zespół"],
    ...(rola !== "hr" ? ([["cele", "cel", rola === "oceniany" ? "Twoje cele" : "Cele zespołu"]] as [Widok, NazwaIkony, string][]) : []),
    ...(rola === "hr"
      ? ([
          ["procesy", "kalendarz", "Procesy i terminy"],
          ["zrodla", "ksiazka", "Źródła i braki"],
        ] as [Widok, NazwaIkony, string][])
      : []),
  ];

  return (
    <div className="powloka">
      <nav className="menu" aria-label="Menu">
        <button type="button" className="znak" onClick={() => onWidok("pulpit")}>
          <img src={znak} alt="" width={40} height={45} />
          <span className="napis">
            Kompas
            <br />
            Kompetencji
          </span>
        </button>
        {pozycje.map(([w, ikona, tekst]) => (
          <button
            key={w}
            type="button"
            className="poz"
            aria-current={widok === w ? "page" : undefined}
            onClick={() => onWidok(w)}
          >
            <Ikona nazwa={ikona} rozmiar={22} />
            <span className="napis">{tekst}</span>
          </button>
        ))}
        <button type="button" className="poz" aria-pressed={asystent} onClick={() => onAsystent(!asystent)}>
          <Ikona nazwa="dymek" rozmiar={22} />
          <span className="napis">Asystent formalny</span>
        </button>
        <div className="menu-dol">
          <div className="konto">
            <span className="inicjaly" aria-hidden="true">
              {login.slice(0, 2).toUpperCase()}
            </span>
            <span className="napis">
              <strong>{login}</strong>
              <span className="meta">{NAZWA_ROLI[rola]}</span>
              <button type="button" className="link" onClick={onWyloguj}>
                Wyloguj
              </button>
            </span>
          </div>
        </div>
      </nav>

      <main className="tresc">
        <div className="kolumna">{children}</div>
      </main>

      <OknoAsystenta otwarte={asystent} onZamknij={() => onAsystent(false)} sciezka={sciezka} pytanie={pytanie} />
    </div>
  );
}
