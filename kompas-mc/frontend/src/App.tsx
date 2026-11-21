import { useCallback, useEffect, useState } from "react";
import { pobierzZrodla, type Zrodla } from "./api";
import { Logowanie, Pracownicy, type Sesja } from "./Konto";
import { Krok1 } from "./Krok1";
import { Krok2 } from "./Krok2";
import { Ocena } from "./Ocena";
import { Rozmowa } from "./Rozmowa";
import { Wynik } from "./Wynik";
import { Arkusz } from "./Arkusz";
import { Wnioski } from "./Wnioski";
import PanelHR from "./PanelHR";
import type { Pracownik, ProcesOceny } from "./api";
import PanelZrodel from "./PanelZrodel";
import { Powloka, type Widok } from "./Powloka";
import { Pulpit } from "./Pulpit";

const KLUCZ_SESJI = "kompas-mc-sesja";

type Etap = "krok2" | "ocena" | "rozmowa" | "wynik" | "arkusz" | "wnioski";

export default function App() {
  const [blad, setBlad] = useState<string | null>(null);
  const [zrodla, setZrodla] = useState<Zrodla | null>(null);
  const [widok, setWidok] = useState<Widok>("pulpit");
  const [asystent, setAsystent] = useState(false);
  const [pytanie, setPytanie] = useState<{ id: number; tekst: string } | null>(null);
  const [oceniany, setOceniany] = useState<Pracownik | null>(null);
  const [proces, setProces] = useState<ProcesOceny | null>(null);
  const [etap, setEtap] = useState<Etap>("krok2");
  const [sesja, setSesja] = useState<Sesja | null>(() => {
    const zapisana = sessionStorage.getItem(KLUCZ_SESJI);
    return zapisana ? (JSON.parse(zapisana) as Sesja) : null;
  });

  const zalogowano = useCallback((s: Sesja) => {
    sessionStorage.setItem(KLUCZ_SESJI, JSON.stringify(s));
    setSesja(s);
  }, []);

  const wyloguj = useCallback(() => {
    sessionStorage.removeItem(KLUCZ_SESJI);
    setSesja(null);
    setWidok("pulpit");
    setAsystent(false);
    setOceniany(null);
    setProces(null);
    setEtap("krok2");
  }, []);

  // Wybór pozycji menu zamyka otwartą ocenę i wraca do listy.
  const przejdz = useCallback((w: Widok) => {
    setWidok(w);
    setOceniany(null);
    setProces(null);
    setEtap("krok2");
  }, []);

  // Pytanie z pulpitu otwiera panel asystenta i trafia do czatu.
  const zapytajAsystenta = useCallback((tekst: string) => {
    setAsystent(true);
    setPytanie({ id: Date.now(), tekst });
  }, []);

  useEffect(() => {
    pobierzZrodla().then(setZrodla).catch(() => setBlad("Brak połączenia z API (port 8002)."));
  }, []);

  if (!sesja) {
    return (
      <main className="logowanie">
        <Logowanie onZalogowano={zalogowano} />
      </main>
    );
  }

  const prowadzi = sesja.uzytkownik.rola === "przelozony";
  // Panel źródeł i braków oraz panel procesów widzi tylko HR/administrator (API też to egzekwuje).
  const widokZrodel = widok === "zrodla" && sesja.uzytkownik.rola === "hr";
  const widokProcesow = widok === "procesy" && sesja.uzytkownik.rola === "hr";

  return (
    <Powloka
      sesja={sesja}
      widok={oceniany ? null : widok}
      onWidok={przejdz}
      onWyloguj={wyloguj}
      asystent={asystent}
      onAsystent={setAsystent}
      sciezka={proces?.sciezka}
      pytanie={pytanie}
    >
      {blad && <p className="blad">{blad}</p>}
      {oceniany && !proces && (
        <Krok1
          token={sesja.token}
          osoba={oceniany}
          moznaProwadzic={prowadzi}
          onWroc={() => setOceniany(null)}
          onDalej={setProces}
        />
      )}
      {oceniany && proces && etap === "krok2" && (
        <Krok2
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={prowadzi}
          onWstecz={() => setProces(null)}
          onDalej={() => setEtap("ocena")}
        />
      )}
      {oceniany && proces && etap === "ocena" && (
        <Ocena
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={prowadzi}
          onWstecz={() => setEtap("krok2")}
          onDalej={() => setEtap("rozmowa")}
        />
      )}
      {oceniany && proces && etap === "rozmowa" && (
        <Rozmowa
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={prowadzi}
          onWstecz={() => setEtap("ocena")}
          onDalej={() => setEtap("wynik")}
        />
      )}
      {oceniany && proces && etap === "wynik" && (
        <Wynik
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={prowadzi}
          onWstecz={() => setEtap("rozmowa")}
          onDalej={() => setEtap("arkusz")}
        />
      )}
      {oceniany && proces && etap === "arkusz" && (
        <Arkusz
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={prowadzi}
          onWstecz={() => setEtap("wynik")}
          onDalej={() => setEtap("wnioski")}
        />
      )}
      {oceniany && proces && etap === "wnioski" && (
        <Wnioski
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={prowadzi}
          onWstecz={() => setEtap("arkusz")}
        />
      )}
      {!oceniany && widokZrodel && <PanelZrodel zrodla={zrodla} token={sesja.token} />}
      {!oceniany && widokProcesow && <PanelHR token={sesja.token} />}
      {!oceniany && widok === "pulpit" && (
        <Pulpit sesja={sesja} onWybierz={setOceniany} onZapytaj={zapytajAsystenta} onWyloguj={wyloguj} />
      )}
      {!oceniany && widok === "pracownicy" && <Pracownicy sesja={sesja} onWyloguj={wyloguj} onWybierz={setOceniany} />}
    </Powloka>
  );
}
