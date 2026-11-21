import { useEffect, useState } from "react";
import { celeApi, pobierzPracownikow, type Cel, type Pracownik } from "./api";
import { CeleOsoby } from "./CeleOsoby";
import { Ikona } from "./Ikona";
import type { Sesja } from "./Konto";
import { Inicjaly, SzkieletListy, WierszListy } from "./Lista";

/**
 * Strona „Cele” (#11). Oceniany widzi swoje cele. Przełożony: lista podwładnych z liczbą celów
 * czekających na jego decyzję → cele osoby. Wejście z karty pracownika podaje od razu ``osoba``.
 */
export function Cele({
  sesja,
  osoba,
  onOsoba,
  onWyloguj,
}: {
  sesja: Sesja;
  osoba: Pracownik | null;
  onOsoba: (p: Pracownik | null) => void;
  onWyloguj: () => void;
}) {
  const [ludzie, setLudzie] = useState<{ p: Pracownik; cele: Cel[] }[] | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const oceniany = sesja.uzytkownik.rola === "oceniany";

  useEffect(() => {
    let aktualne = true;
    pobierzPracownikow(sesja.token)
      .then((lista) => Promise.all(lista.map(async (p) => ({ p, cele: await celeApi.lista(sesja.token, p.osoba_id) }))))
      .then((w) => aktualne && setLudzie(w))
      .catch((e) => (String(e).includes("401") ? onWyloguj() : aktualne && setBlad("Nie udało się pobrać celów.")));
    return () => {
      aktualne = false;
    };
  }, [sesja.token, onWyloguj, osoba]);

  const ja = oceniany ? ludzie?.[0]?.p : null;
  const wybrana = osoba ?? ja ?? null;

  if (wybrana) {
    return (
      <div className="widok">
        <div className="naglowek-widoku">
          {!oceniany && (
            <button type="button" className="link wstecz" onClick={() => onOsoba(null)}>
              <Ikona nazwa="wstecz" /> Cele zespołu
            </button>
          )}
          <h1>{oceniany ? "Twoje cele rozwojowe" : `${wybrana.imie} ${wybrana.nazwisko}`}</h1>
          <p className="meta">
            {oceniany
              ? "Cele omawiasz z przełożonym na początku okresu oceny (rozp. 2016 § 5 ust. 1 pkt 4)."
              : `${wybrana.stanowisko} · cele rozwojowe`}
          </p>
        </div>
        <CeleOsoby sesja={sesja} osoba={wybrana} tytul="Cele" />
      </div>
    );
  }

  return (
    <div className="widok">
      <div className="naglowek-widoku">
        <h1>Cele zespołu</h1>
        <p className="meta">Cele rozwojowe należą do pracownika. Zatwierdzasz je i potwierdzasz ich osiągnięcie.</p>
      </div>
      {blad && <p className="blad">{blad}</p>}
      {!blad && ludzie === null && <SzkieletListy />}
      {ludzie && (
        <div className="lista">
          {ludzie.map(({ p, cele }) => {
            const decyzje = cele.filter((c) => c.status === "propozycja" || (c.zgloszono_osiagniecie && c.status !== "osiągnięty")).length;
            const aktywne = cele.filter((c) => c.status === "zatwierdzony" || c.status === "w_realizacji").length;
            return (
              <WierszListy
                key={p.osoba_id}
                lewa={<Inicjaly imie={p.imie} nazwisko={p.nazwisko} />}
                tytul={`${p.imie} ${p.nazwisko}`}
                znacznik={decyzje > 0 && <span className="status uwaga">{decyzje} do decyzji</span>}
                opis={`${p.stanowisko} · ${cele.length ? `celów: ${cele.length}, w toku: ${aktywne}` : "bez celów"}`}
                onClick={() => onOsoba(p)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
