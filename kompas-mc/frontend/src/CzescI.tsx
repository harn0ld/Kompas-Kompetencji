import { useEffect, useRef, useState } from "react";
import { pobierzCzescIPdf, zapiszZapoznanie, type EtapOsoby, type ProcesOceny, type WyborKroku2 } from "./api";
import { opisBledu } from "./Krok1";
import { PoleDaty, poprawnaData, zapiszPlik } from "./Wynik";
import { data } from "./zespol-dane";

// Zagadnienia rozmowy na początku okresu, rozp. 2016 § 5 ust. 1 pkt 1–4.
const ZAGADNIENIA = [
  "główne obowiązki z opisu stanowiska",
  "kryteria obowiązkowe i wybrane dodatkowe",
  "Twoje oczekiwania co do spełniania kryteriów",
  "cele na okres oceny, jeśli ich wyznaczenie jest uzasadnione",
];

/** Zakończenie części I arkusza oceny okresowej: PDF do podpisu i zapisana data rozmowy i zapoznania
 *  z kryteriami (rozp. 2016 § 5 ust. 1 i 3, § 6). Na końcu okresu („ocena”) część I już istnieje
 *  na papierze, więc przełożony przepisuje z niej datę i przechodzi do rozmowy oceniającej. */
export function ZakonczenieCzesciI({
  token,
  proces,
  wybor,
  cykl,
  moznaProwadzic,
  onZapisano,
  onDalej,
  onPracownik,
  demo = false,
}: {
  token: string;
  proces: ProcesOceny;
  wybor: WyborKroku2;
  cykl: EtapOsoby | null;
  moznaProwadzic: boolean;
  onZapisano: (p: ProcesOceny) => void;
  onDalej: () => void;
  onPracownik: () => void;
  /** Osoba demo (#235): pełna „Rozmowa 1” z drukiem także na końcu okresu, a zapis prowadzi do części II. */
  demo?: boolean;
}) {
  const naKoncuOkresu = cykl?.etap === "ocena";
  // Widok rozmowy na początku okresu (zagadnienia, druk, dzisiejsza data); dla demo zawsze.
  const rozmowa = !naKoncuOkresu || demo;
  // Na początku okresu rozmowa jest dziś; na końcu okresu data pochodzi z podpisanej części I i wyznacza
  // początek okresu w arkuszu („od”), więc pole startuje puste, zamiast podsuwać dzisiejszą datę.
  const [wpisana, setData] = useState<string | null>(wybor.zapoznanie ?? null);
  const dataZapoznania = wpisana ?? (rozmowa ? new Date().toLocaleDateString("sv-SE") : null);
  const [ustalenia, setUstalenia] = useState(wybor.ustalenia ?? "");
  const [czekam, setCzekam] = useState(false);
  const [drukuje, setDrukuje] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);
  const zakonczona = Boolean(wybor.zapoznanie);
  // Panel stoi pod listą kryteriów: po zatwierdzeniu przewiń do niego i ustaw fokus na tytule.
  const tytul = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const bezRuchu = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    tytul.current?.scrollIntoView({ block: "start", behavior: bezRuchu ? "auto" : "smooth" });
    tytul.current?.focus({ preventScroll: true });
  }, []);
  const dodatkowe = wybor.kryteria.filter((k) => k.rodzaj === "DODATKOWE").length;

  async function zapisz() {
    if (!dataZapoznania) return;
    setCzekam(true);
    setBlad(null);
    try {
      onZapisano(await zapiszZapoznanie(token, proces.id, dataZapoznania, ustalenia));
      if (naKoncuOkresu) onDalej();
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setCzekam(false);
    }
  }

  async function drukuj() {
    setDrukuje(true);
    setBlad(null);
    try {
      zapiszPlik(await pobierzCzescIPdf(token, proces.id), `arkusz-${proces.arkusz}-${proces.id}-czesc-I.pdf`);
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setDrukuje(false);
    }
  }

  return (
    <div className="k2-ustalone czesc-i" role="status">
      <h2 ref={tytul} tabIndex={-1}>
        {!rozmowa
          ? "Ustalenia z podpisanej części I"
          : zakonczona
            ? "Rozmowa 1 zakończona: ustalenia na okres"
            : "Rozmowa 1: ustalenia na okres oceny"}
      </h2>
      <p className="meta">
        {wybor.kryteria.length - dodatkowe} kryteriów obowiązkowych
        {dodatkowe > 0 && ` i ${dodatkowe} dodatkowe`}
        {cykl?.termin && ` · ${cykl.termin.nazwa} do ${data(cykl.termin.data)}`}
      </p>
      {!rozmowa ? (
        <p className="meta">
          Część I podpisano na początku okresu. Przepisz z niej datę zapoznania z kryteriami: od niej liczy się okres oceny.
        </p>
      ) : (
        <div>
          <p className="meta">Na rozmowie z ocenianym omów (§ 5 ust. 1):</p>
          <ul className="oc-pytania">
            {ZAGADNIENIA.map((z) => (
              <li key={z}>{z}</li>
            ))}
          </ul>
        </div>
      )}
      {zakonczona ? (
        <p className="sukces">
          {!rozmowa
            ? `Zapoznanie z kryteriami: ${data(wybor.zapoznanie as string)}.`
            : `Część I zakończona ${data(wybor.zapoznanie as string)}. Oryginał do akt osobowych, kopia dla ocenianego (§ 6 ust. 3).`}
        </p>
      ) : (
        moznaProwadzic && (
          <>
            <PoleDaty nazwa="Data rozmowy i zapoznania z kryteriami (§ 6 ust. 2)" wartosc={dataZapoznania} onZmiana={setData} />
            <label className="etykieta oc-uwagi">
              {!rozmowa ? "Cele z podpisanej części I (opcjonalnie, każdy w osobnym wierszu)" : "Oczekiwania i cele na okres (opcjonalnie, § 5 ust. 1 pkt 3–4)"}
              <textarea rows={3} value={ustalenia} onChange={(e) => setUstalenia(e.target.value)} />
            </label>
          </>
        )
      )}
      {zakonczona && wybor.ustalenia && <p className="meta">Oczekiwania i cele: {wybor.ustalenia.split("\n").join(" · ")}</p>}
      {blad && <p className="blad">{blad}</p>}
      <div className="k2-akcje">
        <button type="button" className="link k2-do-pracownika" onClick={onPracownik}>
          Wróć do pracownika
        </button>
        {cykl?.etap !== "brak_danych" && rozmowa && (
          <button type="button" className="jasny" disabled={drukuje} onClick={drukuj}>
            {drukuje ? "Przygotowuję PDF…" : "Pobierz część I do podpisu"}
          </button>
        )}
        {moznaProwadzic && !zakonczona && (
          <button type="button" disabled={czekam || !dataZapoznania || !poprawnaData(dataZapoznania)} onClick={zapisz}>
            {czekam
              ? "Zapisuję…"
              : naKoncuOkresu
                ? demo
                  ? "Zapisz część I i przejdź dalej"
                  : "Zapisz i przejdź do rozmowy oceniającej"
                : "Zapisz i zakończ część I"}
          </button>
        )}
        {zakonczona && naKoncuOkresu && (
          <button type="button" onClick={onDalej}>
            Dalej: rozmowa oceniająca
          </button>
        )}
      </div>
    </div>
  );
}
