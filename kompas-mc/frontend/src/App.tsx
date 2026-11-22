import { useCallback, useEffect, useState } from "react";
import { KLUCZ_SESJI, pobierzZrodla, type Zrodla } from "./api";
import { Logowanie, type Sesja } from "./Konto";
import { Krok1 } from "./Krok1";
import { Krok2 } from "./Krok2";
import { Ocena } from "./Ocena";
import { Wynik } from "./Wynik";
import { Arkusz } from "./Arkusz";
import { Wnioski } from "./Wnioski";
import { Pierwsza } from "./Pierwsza";
import PanelMetodyki from "./PanelMetodyki";
import PanelHR from "./PanelHR";
import Rejestr from "./Rejestr";
import { pobierzPracownikow, pobierzWynik, type Pracownik, type ProcesOceny } from "./api";
import PanelZrodel from "./PanelZrodel";
import { Powloka, type Widok } from "./Powloka";
import { Pulpit } from "./Pulpit";
import { Zespol } from "./Zespol";
import { KartaPracownika } from "./KartaPracownika";
import { Cele } from "./Cele";
import { CeleOsoby } from "./CeleOsoby";
import { MojaSamoocena } from "./Samoocena";
import { ListaPracownikow } from "./ListaPracownikow";
import type { FiltrPracownikow } from "./zespol-dane";


type Etap = "krok2" | "ocena" | "wynik" | "arkusz" | "wnioski";

export default function App() {
  const [blad, setBlad] = useState<string | null>(null);
  // Kryteria otwarte z rozmowy: tylko podgląd części I (§ 5–6, § 9 ust. 3).
  const [podgladCzesciI, setPodgladCzesciI] = useState(false);
  const [zrodla, setZrodla] = useState<Zrodla | null>(null);
  const [widok, setWidok] = useState<Widok>("pulpit");
  const [asystent, setAsystent] = useState(false);
  const [pytanie, setPytanie] = useState<{ id: number; tekst: string } | null>(null);
  // Karta pracownika otwiera się przed krokiem 1; „Następny krok” na karcie ustawia ocenianego.
  const [karta, setKarta] = useState<Pracownik | null>(null);
  // „Moja samoocena” (#9): proces otwarty z karty na koncie pracownika.
  const [samoocena, setSamoocena] = useState<number | null>(null);
  // Filtr listy Pracownicy ustawiany z Zespołu (kliknięcie liczby albo komórki) i z pulpitu.
  const [filtr, setFiltr] = useState<FiltrPracownikow>({});
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
    setKarta(null);
    setSamoocena(null);
    setOceniany(null);
    setProces(null);
    setEtap("krok2");
    setFiltr({});
    setPytanie(null);
    setPodgladCzesciI(false);
  }, []);

  // Wybór pozycji menu zamyka otwartą ocenę i wraca do listy.
  const przejdz = useCallback((w: Widok) => {
    setWidok(w);
    setFiltr({});
    setKarta(null);
    setSamoocena(null);
    setOceniany(null);
    setProces(null);
    setEtap("krok2");
  }, []);

  const doPracownikow = useCallback((f: FiltrPracownikow = {}) => {
    setWidok("pracownicy");
    setFiltr(f);
    setKarta(null);
    setOceniany(null);
  }, []);

  // Pytanie z pulpitu otwiera panel asystenta i trafia do czatu.
  const zapytajAsystenta = useCallback((tekst: string) => {
    setAsystent(true);
    setPytanie({ id: Date.now(), tekst });
  }, []);

  useEffect(() => {
    pobierzZrodla().then(setZrodla).catch(() => setBlad("Brak połączenia z API (port 8002)."));
  }, []);

  // „Twoje dane” pracownika (#183): od razu własna karta, bez tabeli z jednym wierszem.
  const pracownik = sesja?.uzytkownik.rola === "oceniany";
  useEffect(() => {
    if (!sesja || !pracownik || widok !== "pracownicy" || karta) return;
    let aktualne = true;
    pobierzPracownikow(sesja.token)
      .then((lista) => {
        if (!aktualne) return;
        const ja = lista.find((p) => p.osoba_id === sesja.uzytkownik.osoba_id);
        if (ja) setKarta(ja);
        else setBlad("Nie znaleziono Twoich danych.");
      })
      .catch((err) => (String(err).includes("401") ? wyloguj() : setBlad("Nie udało się pobrać Twoich danych.")));
    return () => {
      aktualne = false;
    };
  }, [sesja, pracownik, widok, karta, wyloguj]);

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
  const widokRejestru = widok === "rejestr" && sesja.uzytkownik.rola === "hr";

  // #49: karta otwiera bieżący krok procesu w toku zamiast kroku 1; bez procesu krok 1.
  // Krok 7 okresowej: arkusz, gdy wynik jest zapisany i aktualny, inaczej ekran wyniku.
  // Pierwsza ocena: od kroku 6 (wynik zapisany albo rozmowa zakończona) ekran Pierwsza.tsx.
  /** `wymus`: etap wybrany na karcie (#55), np. kryteria procesu, który jest już dalej. */
  const otworzProces = async (osoba: Pracownik, p: ProcesOceny | null, wymus?: Etap) => {
    const k = p?.krok ?? 0;
    const nowyEtap: Etap = wymus ??
      (k >= 8
        ? "wnioski"
        : k === 7 && p?.sciezka === "okresowa"
          ? await pobierzWynik(sesja.token, p.id).then(
              (w): Etap => (w.zapisany ? "arkusz" : "wynik"),
              (): Etap => "wynik",
            )
          : k >= 6
            ? "wynik"
            : k >= 3 || p?.krok2?.zapoznanie
              ? // Część I zakończona (data zapoznania z kryteriami, § 6): „Zakończ ocenę” otwiera rozmowę; niezamknięta część I → krok 2.
                // Kryteria z części I widać w „Zobacz kryteria (część I)” albo z etapu na karcie.
                "ocena"
              : "krok2");
    setEtap(nowyEtap);
    setPodgladCzesciI(false);
    setProces(p);
    setOceniany(osoba);
  };

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
          moznaProwadzic={prowadzi && !podgladCzesciI}
          onWstecz={() => setProces(null)}
          onDalej={() => {
            setPodgladCzesciI(false);
            setEtap("ocena");
          }}
          onPracownik={() => {
            setProces(null);
            setOceniany(null);
            setEtap("krok2");
          }}
        />
      )}
      {oceniany && proces && etap === "ocena" && (
        <Ocena
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={prowadzi}
          onWstecz={() => {
            // Z rozmowy kryteria tylko do podglądu: część I ustalono na początku okresu (§ 5–6, § 9 ust. 3).
            setPodgladCzesciI(true);
            setEtap("krok2");
          }}
          onDalej={() => setEtap("wynik")}
        />
      )}
      {oceniany && proces && (etap === "wynik" || etap === "arkusz" || etap === "wnioski") && (() => {
        const Ekran = proces.sciezka === "pierwsza" ? Pierwsza : etap === "arkusz" ? Arkusz : Wynik;
        return (
          <div hidden={etap === "wnioski"}>
            <Ekran
              key={proces.id}
              token={sesja.token}
              osoba={oceniany}
              proces={proces}
              moznaProwadzic={prowadzi}
              zalogowanyId={sesja.uzytkownik.osoba_id}
              onWstecz={() => setEtap("ocena")}
              onZmienOcene={proces.status === "W_TOKU" ? () => setEtap("ocena") : undefined}
              onDalej={() => setEtap("wnioski")}
            />
          </div>
        );
      })()}
      {oceniany && proces && etap === "wnioski" && (
        <Wnioski
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={prowadzi}
          onWstecz={() => setEtap(proces.sciezka === "pierwsza" ? "wynik" : "arkusz")}
        />
      )}
      {karta && samoocena !== null && (
        <MojaSamoocena token={sesja.token} osoba={karta} procesId={samoocena} onWroc={() => setSamoocena(null)} />
      )}
      {karta && !oceniany && samoocena === null && (
        <KartaPracownika
          sesja={sesja}
          osoba={karta}
          onWroc={() => (pracownik ? przejdz("pulpit") : setKarta(null))}
          onOcen={(p, e) => otworzProces(karta, p, e)}
          onSamoocena={setSamoocena}
          onZapytaj={zapytajAsystenta}
          onWyloguj={wyloguj}
          cele={<CeleOsoby sesja={sesja} osoba={karta} maks={pracownik ? undefined : 3} />}
        />
      )}
      {!karta && !oceniany && widokZrodel && <h1 className="tytul-widoku">Źródła i braki</h1>}
      {!karta && !oceniany && widokZrodel && <PanelZrodel zrodla={zrodla} token={sesja.token} />}
      {!karta && !oceniany && widokZrodel && <PanelMetodyki token={sesja.token} mozeZarzadzac />}
      {!karta && !oceniany && widokProcesow && <h1 className="tytul-widoku">Procesy i terminy</h1>}
      {!karta && !oceniany && widokProcesow && <PanelHR token={sesja.token} />}
      {!karta && !oceniany && widokRejestru && <h1 className="tytul-widoku">Rejestr operacji</h1>}
      {!karta && !oceniany && widokRejestru && <Rejestr token={sesja.token} />}
      {!karta && !oceniany && widok === "pulpit" && (
        <Pulpit
          sesja={sesja}
          onWybierz={setKarta}
          onWyloguj={wyloguj}
          onZespol={() => przejdz("zespol")}
          onPracownicy={() => przejdz("pracownicy")}
          onCele={() => przejdz("cele")}
        />
      )}
      {!karta && !oceniany && widok === "zespol" && <Zespol sesja={sesja} onWyloguj={wyloguj} onPracownicy={doPracownikow} onWybierz={setKarta} />}
      {!karta && !oceniany && widok === "cele" && <Cele sesja={sesja} onWyloguj={wyloguj} />}
      {!karta && !oceniany && !pracownik && widok === "pracownicy" && (
        <ListaPracownikow sesja={sesja} filtr={filtr} onFiltr={setFiltr} onWyloguj={wyloguj} onWybierz={setKarta} />
      )}
    </Powloka>
  );
}
