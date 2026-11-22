import { useEffect, useState, type ReactNode } from "react";
import {
  pobierzCykl,
  pobierzKrok1,
  pobierzMapeKompetencji,
  pobierzNotatki,
  pobierzOcene,
  pobierzPracownikow,
  pobierzProcesy,
  pobierzSamoocene,
  pobierzTerminy,
  type AnalizaKroku1,
  type EtapOsoby,
  type MapaKompetencji,
  type Notatka,
  type Pracownik,
  type ProcesOceny,
  type Samoocena,
  type StanOceny,
  type TerminProcesu,
} from "./api";
import { Ikona } from "./Ikona";
import type { Sesja } from "./Konto";
import { SzkieletListy, WierszListy } from "./Lista";
import { OcenyCzastkowe, nazwaKryterium } from "./Kompetencje";
import { OpisOsoby } from "./OpisOsoby";
import { data, kiedy, lat, lataStazu, podzial } from "./zespol-dane";
import "./widoki.css";

/**
 * Karta pracownika (przed krokiem 1): kim jest, jak idzie ocena, co dalej. Dane z QNT (kadry), z analizy
 * opisu stanowiska (krok 1), z procesu i jego terminu, z ocen kryteriów i z notatek przełożonego.
 * Każda sekcja pojawia się tylko, gdy API ma dla niej dane; jedyny przycisk główny jest w „Następny krok”.
 */

/**
 * Trzy etapy cyklu: jeden arkusz wypełniany w dwóch momentach – „Rozpocznij ocenę” (część I, rozp. 2016 § 5–7;
 * pierwsza: rozmowa wstępna, rozp. 2015 § 3–4) i „Zakończ ocenę” (część II: rozmowa oceniająca i ocena na piśmie,
 * § 10–11), między nimi okres oceny. Nazwy jak na grafice organizatora i w poradniku KPRM (tab. 1, wzór s. 42).
 * Kolejność = indeks etapu z /api/cykl. Tak samo dla arkuszy A, B i C.
 */
const ETAPY_CYKLU: Record<"okresowa" | "pierwsza", [string, string, string]> = {
  okresowa: ["Rozpoczęcie oceny", "Okres oceny", "Zakończenie oceny"],
  pierwsza: ["Rozpoczęcie: rozmowa wstępna", "Okres przed pierwszą oceną", "Zakończenie oceny"],
};
const PODPOWIEDZI_PIERWSZA = [
  "Kiedy przeprowadza się rozmowę wstępną?",
  "Kto sporządza pierwszą ocenę?",
  "Co się dzieje po negatywnej pierwszej ocenie?",
];
const INDEKS_ETAPU: Record<EtapOsoby["etap"], number> = { kryteria: 0, okres: 1, ocena: 2, brak_danych: -1 };

const PODPOWIEDZI: Record<EtapOsoby["etap"], string[]> = {
  // Rozmowa wstępna to pierwsza ocena (§ 3 rozp. 2015); przy okresowej pytanie o termin kryteriów (§ 7 rozp. 2016, FAQ).
  kryteria: ["Jak ustalić kryteria oceny okresowej?", "Ile kryteriów dodatkowych można wybrać?", "W jakim czasie od poprzedniej oceny ustala się kryteria?"],
  okres: ["Co zrobić, gdy zmienia się oceniający?", "Kiedy można przesunąć termin oceny?", "Jak dokumentować przykłady zachowań?"],
  ocena: ["Co omawia się na rozmowie oceniającej?", "Kiedy ocena okresowa jest negatywna?", "Ile dni ma pracownik na sprzeciw od oceny okresowej?"],
  brak_danych: ["Kto podlega ocenie okresowej?", "Kto podlega pierwszej ocenie?", "Co zrobić, gdy brakuje danych kadrowych?"],
};

interface Dane {
  analiza: AnalizaKroku1 | null;
  proces: ProcesOceny | null;
  termin: TerminProcesu | null;
  ocena: StanOceny | null;
  /** Własna samoocena (konto pracownika); dla innych ról null. */
  samoocena: Samoocena | null;
  notatki: Notatka[];
  przelozony: Pracownik | null;
  /** Etap cyklu i następna czynność z /api/cykl (#23). */
  cykl: EtapOsoby | null;
  /** Mapa kompetencji (#33): tylko przełożony; oceny cząstkowe ostatniej oceny z akt. */
  mapa: MapaKompetencji | null;
  /** Ostatnia ocena okresowa zakończona w aplikacji (zgłoszenie 175): podgląd poziomów i samooceny tego cyklu. */
  zakonczony: ProcesOceny | null;
}

export function KartaPracownika({
  sesja,
  osoba,
  onWroc,
  onOcen,
  onSamoocena,
  onZapytaj,
  onWyloguj,
  cele,
}: {
  sesja: Sesja;
  osoba: Pracownik;
  onWroc: () => void;
  /** Proces w toku (#49): App otwiera jego bieżący krok; null = krok 1; "krok2" = kryteria procesu (etap na karcie, #55). */
  onOcen: (proces: ProcesOceny | null, etap?: "krok2" | "ocena") => void;
  /** Pracownik otwiera „Moją samoocenę” procesu (#9). */
  onSamoocena?: (procesId: number) => void;
  /** Sekcja celów rozwojowych osoby (#11, komponent z gałęzi celów); bez niej sekcji nie ma. */
  cele?: ReactNode;
  onZapytaj: (pytanie: string) => void;
  onWyloguj: () => void;
}) {
  const [dane, setDane] = useState<Dane | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const token = sesja.token;
  const prowadzi = sesja.uzytkownik.rola === "przelozony";

  useEffect(() => {
    let aktualne = true;
    (async () => {
      try {
        const [analiza, procesy, terminy, ludzie, notatki, cykl] = await Promise.all([
          pobierzKrok1(token, osoba.osoba_id).catch(() => null),
          pobierzProcesy(token),
          pobierzTerminy(token).catch(() => []),
          pobierzPracownikow(token),
          // Notatki widzi tylko przełożony; HR i oceniany nie pytają (API dałoby 403).
          prowadzi ? pobierzNotatki(token, osoba.osoba_id).catch(() => []) : Promise.resolve([] as Notatka[]),
          pobierzCykl(token).catch(() => []),
        ]);
        const mapa = prowadzi ? await pobierzMapeKompetencji(token).catch(() => null) : null;
        const wlasne = procesy.filter((p) => p.osoba_id === osoba.osoba_id);
        const proces = wlasne.find((p) => p.status === "W_TOKU") ?? wlasne[wlasne.length - 1] ?? null;
        // Samoocena: tylko konto pracownika (własny proces); przed krokiem 2 API zwraca 409.
        const rola = sesja.uzytkownik.rola;
        const samoocena = proces && rola === "oceniany" ? await pobierzSamoocene(token, proces.id).catch(() => null) : null;
        // Ocena kryteriów istnieje dopiero po zapisaniu kroku 2. HR nie widzi treści ocen, pracownik dopiero po
        // przekazaniu samooceny albo zakończeniu – inaczej API odpowiada 403 i odmowa trafia do rejestru (przegląd serwera, zgłoszenie 122).
        const widziOcene = rola === "przelozony" || (rola === "oceniany" && (proces?.status !== "W_TOKU" || samoocena?.status === "przekazana"));
        const ocena = proces?.krok2 && widziOcene ? await pobierzOcene(token, proces.id).catch(() => null) : null;
        if (!aktualne) return;
        setDane({
          analiza,
          proces,
          termin: (proces && terminy.find((t) => t.proces_id === proces.id)) || null,
          ocena,
          notatki,
          przelozony: ludzie.find((p) => p.osoba_id === osoba.przelozony_id) ?? null,
          samoocena,
          cykl: cykl.find((c) => c.osoba_id === osoba.osoba_id) ?? null,
          mapa,
          zakonczony: [...wlasne].reverse().find((p) => p.status === "ZAKONCZONY" && p.sciezka === "okresowa") ?? null,
        });
      } catch (err) {
        if (String(err).includes("401")) onWyloguj();
        else if (aktualne) setBlad("Nie udało się pobrać danych pracownika.");
      }
    })();
    return () => {
      aktualne = false;
    };
  }, [token, osoba, onWyloguj]);

  const { wydzial, departament } = podzial(osoba.komorka);
  const staz = lataStazu(osoba.data_zatrudnienia);
  const przelozonyTo =
    osoba.przelozony_id === sesja.uzytkownik.osoba_id
      ? "Ty"
      : dane?.przelozony
        ? `${dane.przelozony.imie} ${dane.przelozony.nazwisko}`
        : null;
  const wToku = dane?.proces?.status === "W_TOKU" ? dane.proces : null;
  /** Etap cyklu (#55): ocena → bieżący krok procesu (#49), kryteria i okres → krok 2, bez procesu → krok 1. */
  const otworzEtap = (i: number) => (i === 2 || !wToku ? onOcen(wToku) : onOcen(wToku, "krok2"));

  return (
    <div className="widok karta">
      <button type="button" className="link wstecz" onClick={onWroc}>
        <Ikona nazwa="wstecz" rozmiar={20} />
        Wróć
      </button>

      <div className="karta-glowa">
        <span className="inicjaly duze" aria-hidden="true">
          {osoba.imie.charAt(0)}
          {osoba.nazwisko.charAt(0)}
        </span>
        <div>
          <h1>
            {osoba.imie} {osoba.nazwisko}
          </h1>
          <p className="opis">
            {osoba.stanowisko} · {wydzial}
          </p>
          <OpisOsoby sesja={sesja} osoba={osoba} />
        </div>
      </div>

      {blad && <p className="blad">{blad}</p>}
      {!blad && !dane && <SzkieletListy wiersze={3} />}

      {dane && (
        <div className="dwie">
          <div className="sekcje-karty">
            <Cykl
              dane={dane}
              osoba={osoba}
              sciezka={dane.cykl?.sciezka ?? dane.proces?.sciezka ?? dane.analiza?.sciezka.proponowana ?? null}
              onEtap={prowadzi ? otworzEtap : undefined}
              wToku={wToku !== null}
            />
            <OcenyKryteriow
              ocena={dane.ocena}
              osoba={osoba}
              mapa={dane.mapa}
              pierwsza={(dane.cykl?.sciezka ?? dane.proces?.sciezka) === "pierwsza"}
              // Szczegóły poprzedniej oceny zakończonej w aplikacji: przełożony i pracownik (HR nie widzi treści ocen).
              onSzczegoly={dane.zakonczony && sesja.uzytkownik.rola !== "hr" ? () => onOcen(dane.zakonczony, "ocena") : undefined}
              onSamoocena={
                dane.zakonczony && sesja.uzytkownik.rola === "oceniany" && onSamoocena
                  ? () => onSamoocena(dane.zakonczony!.id)
                  : undefined
              }
            />
            {/* Karol 22.11: opis stanowiska (co oceniamy) przed celami rozwojowymi. */}
            {dane.analiza?.osp && <OpisStanowiska osp={dane.analiza.osp} />}
            {cele}

            {dane.notatki.length > 0 && (
              <div className="sekcja">
                <h2>Notatki przełożonego</h2>
                <ul className="notatki">
                  {dane.notatki.map((n) => (
                    <li key={n.id}>
                      <span className="meta">
                        {data(n.czas)} · {n.autor}
                      </span>
                      <p>{n.tresc}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <aside className="bok-karty">
            {dane.samoocena && onSamoocena ? (
              <NastepnySamoocena s={dane.samoocena} onOtworz={() => onSamoocena(dane.samoocena!.proces_id)} />
            ) : (
              <NastepnyKrok
                dane={dane}
                prowadzi={prowadzi}
                onOcen={() => onOcen(wToku, dane.cykl?.etap === "kryteria" ? "krok2" : undefined)}
                onZobacz={() => onOcen(dane.proces)}
                przelozony={dane.przelozony}
                hr={sesja.uzytkownik.rola === "hr"}
              />
            )}

            <div className="sekcja">
              <h2>Dane kadrowe</h2>
              <dl className="dane-kadrowe">
                <dt>Zatrudnienie</dt>
                <dd>
                  od {data(osoba.data_zatrudnienia)},{" "}
                  {osoba.korpus === "urzednik_sc"
                    ? "na podstawie mianowania"
                    : `na czas ${osoba.rodzaj_umowy === "nieokreslony" ? "nieokreślony" : "określony"}`}
                  {osoba.data_konca_zatrudnienia && <>, do {data(osoba.data_konca_zatrudnienia)}</>}
                </dd>
                <dt>Staż</dt>
                <dd>{staz < 1 ? "poniżej roku" : lat(staz)}</dd>
                <dt>Korpus służby cywilnej</dt>
                <dd>{osoba.korpus === "urzednik_sc" ? "urzędnik" : "pracownik"}</dd>
                <dt>Komórka</dt>
                <dd>
                  {wydzial}
                  <br />
                  <span className="meta">{departament}</span>
                </dd>
                {przelozonyTo && (
                  <>
                    <dt>Przełożony</dt>
                    <dd>{przelozonyTo}</dd>
                  </>
                )}
                <dt>Kieruje pracownikami</dt>
                <dd>{osoba.kieruje_pracownikami ? "tak" : "nie"}</dd>
                {osoba.zmiana_oceniajacego && (
                  <>
                    <dt>Zmiana oceniającego</dt>
                    <dd>{data(osoba.zmiana_oceniajacego.data)}</dd>
                  </>
                )}
                {osoba.absolwent_ksap && (
                  <>
                    <dt>Absolwent KSAP</dt>
                    <dd>tak{osoba.wniosek_o_mianowanie ? ", z wnioskiem o mianowanie" : ""}</dd>
                  </>
                )}
                {osoba.zastepstwo && (
                  <>
                    <dt>Zastępstwo</dt>
                    <dd>tak</dd>
                  </>
                )}
                {(osoba.nieobecnosci?.length ?? 0) > 0 && (
                  <>
                    <dt>Nieobecności</dt>
                    <dd>
                      {osoba.nieobecnosci!.map((n) => (
                        <span key={n.od} className="blok">
                          {n.rodzaj}: {data(n.od)}–{data(n.do)}
                        </span>
                      ))}
                    </dd>
                  </>
                )}
              </dl>
              <p className="meta zero">Źródło: kartoteka QNT</p>
            </div>

            <div className="sekcja">
              <h2>Zapytaj asystenta</h2>
              <div className="lista ciasna">
                {((dane.cykl?.sciezka ?? dane.proces?.sciezka) === "pierwsza"
                  ? PODPOWIEDZI_PIERWSZA
                  : PODPOWIEDZI[dane.cykl?.etap ?? "ocena"]
                ).map((q) => (
                  <WierszListy key={q} maly lewa={<Ikona nazwa="pytanie" />} tytul={q} onClick={() => onZapytaj(q)} />
                ))}
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

/**
 * Cykl oceny w trzech etapach z rozporządzeń i zdanie „Teraz: … do … · Potem: …” (rada UX 21.11).
 * Etap i termin podaje /api/cykl; front nic nie liczy. Przełożony klika etap zrobiony albo bieżący i przechodzi
 * do jego kroku (#55). Pod etapami poprzednie oceny z akt, bo są częścią tej samej oceny (Karol 21.11).
 */
function Cykl({
  dane,
  osoba,
  sciezka,
  onEtap,
  wToku,
}: {
  dane: Dane;
  osoba: Pracownik;
  sciezka: "okresowa" | "pierwsza" | null;
  onEtap?: (i: number) => void;
  /** Proces w toku w aplikacji; bez niego klikalny jest tylko bieżący etap, który zaczyna ocenę. */
  wToku: boolean;
}) {
  const c = dane.cykl;
  const etapy = ETAPY_CYKLU[sciezka ?? "okresowa"];
  // Ocena w toku przed zapoznaniem z kryteriami stoi na rozpoczęciu, nawet gdy termin z kartoteki jest dalej.
  const p = dane.proces;
  // Pierwsza ocena: rozpoczęcie kończy zapis rozmowy wstępnej, czyli wyjście cyklu z etapu „kryteria” (#99).
  const rozpoczecieWToku =
    p?.status === "W_TOKU" && p.krok < 3 && !p.krok2?.zapoznanie && !(p.sciezka === "pierwsza" && c && c.etap !== "kryteria");
  const biezacy = rozpoczecieWToku ? 0 : c ? INDEKS_ETAPU[c.etap] : -1;
  // Karol 22.11 02:13: etap rozwija się na miejscu i pokazuje, co ustalono; przejście do ekranu jest w środku.
  const [otwarty, setOtwarty] = useState<number | null>(null);
  const arkusz = sciezka !== "pierwsza" ? dane.analiza?.arkusz_okresowy : null;
  return (
    <div className="sekcja cykl">
      <h2>
        {sciezka === "pierwsza" ? "Pierwsza ocena" : "Ocena okresowa"}
        {/* Arkusz jako dopisek (Karol 21.11: „aż takie duże?”); uzasadnienie z przepisem jest w kroku 1. */}
        {arkusz?.arkusz && <span className="arkusz-dopisek"> · arkusz {arkusz.arkusz}</span>}
      </h2>
      {/* Braki dat w kartotece to język przepisów; przełożonemu wystarczy jedna linia, szczegóły po rozwinięciu. */}
      {c && c.braki.length > 0 && (
        <details className="braki-karty">
          <summary>
            W kartotece QNT brakuje {c.braki.length === 1 ? "jednej daty" : `${c.braki.length} dat`}, więc termin może być
            niepełny
          </summary>
          <ul>
            {c.braki.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </details>
      )}
      {c && biezacy >= 0 && (
        <ol className="etapy">
          {etapy.map((nazwa, i) => {
            const stan = i < biezacy ? "zrobiony" : i === biezacy ? "biezacy" : "przyszly";
            const opis =
              stan === "zrobiony"
                ? i === 0 && c.kryteria_ustalone
                  ? `ustalone ${data(c.kryteria_ustalone)}`
                  : "zrobione"
                : stan === "biezacy"
                  ? rozpoczecieWToku
                    ? "w toku"
                    : c.termin
                    ? `do ${data(c.termin.data)}`
                    : "teraz"
                  : "";
            // Przejście do ekranu tylko do oceny w aplikacji (albo bieżącej czynności poza okresem);
            // nigdy nie otwiera nowej oceny z etapu zrobionego poza aplikacją.
            const doEkranu = onEtap && stan !== "przyszly" && (wToku || (stan === "biezacy" && c.etap !== "okres"));
            const klik = stan !== "przyszly";
            const tresc = (
              <>
                <span className={`znak-etapu ${stan}`} aria-hidden="true">
                  {stan === "zrobiony" ? <Ikona nazwa="ok" rozmiar={16} /> : i + 1}
                </span>
                <span className="nazwa-etapu">{nazwa}</span>
                <span className="meta">{opis}</span>
                {klik && <span className={otwarty === i ? "strzalka obrot" : "strzalka"}><Ikona nazwa="dalej" rozmiar={20} /></span>}
              </>
            );
            return (
              <li key={nazwa} className={stan} aria-current={stan === "biezacy" ? "step" : undefined}>
                {klik ? (
                  <button
                    type="button"
                    className="etap"
                    aria-expanded={otwarty === i}
                    onClick={() => setOtwarty(otwarty === i ? null : i)}
                  >
                    {tresc}
                  </button>
                ) : (
                  <div className="etap">{tresc}</div>
                )}
                {otwarty === i && (
                  <SzczegolyEtapu
                    i={i}
                    pierwsza={sciezka === "pierwsza"}
                    c={c}
                    p={p}
                    osoba={osoba}
                    onOtworz={doEkranu ? () => onEtap!(i) : undefined}
                  />
                )}
              </li>
            );
          })}
        </ol>
      )}
      {/* Pierwsza ocena nie ma samooceny ani wcześniejszych ocen (Karol 22.11: „po co te wszystkie?”). */}
      {sciezka !== "pierwsza" && <LiniaSamooceny ocena={dane.ocena} />}
    </div>
  );
}

/** Co ustalono w etapie: kryteria i zapoznanie (część I), okres od–do, stan zakończenia; przejście do ekranu, gdy jest. */
function SzczegolyEtapu({
  i,
  pierwsza,
  c,
  p,
  osoba,
  onOtworz,
}: {
  i: number;
  pierwsza: boolean;
  c: EtapOsoby;
  p: ProcesOceny | null;
  osoba: Pracownik;
  onOtworz?: () => void;
}) {
  const wybor = p?.krok2;
  const poczatek = wybor?.zapoznanie ?? c.kryteria_ustalone;
  const wiersze: [string, ReactNode][] = [];
  if (i === 0) {
    if (pierwsza) {
      if (poczatek) wiersze.push(["Rozmowa wstępna", data(poczatek)]);
    } else {
      // Nazwy z arkusza bywają wersalikami; na karcie zdaniowo („Zarządzanie ludźmi”).
      const nazwa = (n: string) => n.charAt(0).toUpperCase() + n.slice(1).toLowerCase();
      const obow = wybor?.kryteria.filter((k) => k.rodzaj === "OBOWIAZKOWE").map((k) => nazwa(k.nazwa)) ?? [];
      const dod = wybor?.kryteria.filter((k) => k.rodzaj === "DODATKOWE").map((k) => nazwa(k.nazwa)) ?? [];
      if (obow.length) wiersze.push(["Kryteria obowiązkowe", obow.join(", ")]);
      if (dod.length) wiersze.push(["Kryteria dodatkowe", dod.join(", ")]);
      if (poczatek) wiersze.push(["Zapoznanie z kryteriami", data(poczatek)]);
    }
    if (!wybor)
      wiersze.push(["Kryteria", poczatek ? "ustalone poza aplikacją, treść w aktach osobowych" : "ustalone poza aplikacją, daty nie ma w kartotece QNT"]);
  } else if (i === 1) {
    // Okres liczy się od zakończenia poprzedniej oceny (art. 81 ustawy), gdy kartoteka nie ma daty ustalenia kryteriów.
    const od = poczatek ? data(poczatek) : osoba.ostatnia_ocena_okresowa ? `${data(osoba.ostatnia_ocena_okresowa.data)} (poprzednia ocena)` : null;
    wiersze.push(["Okres", `${od ? `od ${od} ` : ""}${c.termin ? `do ${data(c.termin.data)}` : ""}`.trim() || "brak dat w kartotece"]);
  } else {
    if (c.termin) wiersze.push([c.termin.nazwa.replace(/^./, (x) => x.toUpperCase()), `do ${data(c.termin.data)}`]);
    if (p && p.status === "W_TOKU" && p.krok >= 3) wiersze.push(["Stan", p.krok >= 6 ? "ocena na piśmie" : "rozmowa oceniająca"]);
  }
  return (
    <div className="szczegoly-etapu">
      {wiersze.length > 0 ? (
        <dl>
          {wiersze.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="meta zero">Brak danych z tego etapu w aplikacji.</p>
      )}
      {onOtworz && (
        <button type="button" className="link" onClick={onOtworz}>
          {i === 0 ? (pierwsza ? "Otwórz rozmowę wstępną" : "Otwórz część I") : "Otwórz ocenę"}
        </button>
      )}
    </div>
  );
}

/**
 * Oceny kryteriów (zgłoszenie 100): linia poprzedniej oceny z kartoteki QNT i paski – bieżącej oceny, gdy przełożony już
 * zdecydował o punktach, inaczej ostatniej oceny okresowej (punkty tylko dla przełożonego, mapa). Bez danych – nic.
 */
function OcenyKryteriow({
  ocena,
  osoba,
  mapa,
  pierwsza,
  onSzczegoly,
  onSamoocena,
}: {
  ocena: StanOceny | null;
  osoba: Pracownik;
  mapa: MapaKompetencji | null;
  pierwsza: boolean;
  onSzczegoly?: () => void;
  onSamoocena?: () => void;
}) {
  const o = pierwsza ? null : osoba.ostatnia_ocena_okresowa;
  const p = pierwsza ? null : osoba.pierwsza_ocena;
  const biezace = ocena?.kryteria.filter((k) => k.decyzja) ?? [];
  const maPunkty = mapa?.osoby.some((x) => x.osoba_id === osoba.osoba_id && x.zrodlo === "ostatnia_ocena");
  const poprzednieSlupki = o && biezace.length === 0 && maPunkty ? <OcenyCzastkowe mapa={mapa} osoba={osoba} bezNaglowka /> : null;
  if (!o && !p && biezace.length === 0) return null;
  const max = ocena ? Math.max(...ocena.skala.punkty) : 9;
  return (
    <div className="sekcja oceny-kryteriow">
      {/* Bez punktów (HR, pracownik przed zakończeniem) jest tylko wynik i data – nagłówek mówi, co widać (Helix G2). */}
      <h2>{biezace.length > 0 || poprzednieSlupki ? "Oceny kryteriów" : "Poprzednia ocena"}</h2>
      {(o || p) && (
        <div className="poprzednie">
          {o && (
            <p className="zero">
              Poprzednia ocena okresowa <span className={`status ${o.wynik}`}>{o.wynik}</span>{" "}
              <span className="meta">sporządzona {data(o.data)}</span>
            </p>
          )}
          {/* Zgłoszenie 175: wejście w szczegóły (poziomy wskaźników, samoocena) poprzedniego cyklu, tylko do odczytu. */}
          {o && (onSzczegoly || onSamoocena) && (
            <div className="akcje-poprzedniej">
              {onSzczegoly && (
                <button type="button" className="link" onClick={onSzczegoly}>
                  Szczegóły poprzedniej oceny
                </button>
              )}
              {onSamoocena && (
                <button type="button" className="link" onClick={onSamoocena}>
                  Twoja samoocena z tego cyklu
                </button>
              )}
            </div>
          )}
          {o && !onSzczegoly && !onSamoocena && (
            <p className="meta zero">Szczegółowe odpowiedzi z tej oceny są w aktach osobowych; kartoteka QNT ma tylko podsumowanie.</p>
          )}
          {p && (
            <p className="zero">
              Pierwsza ocena{" "}
              <span className="meta">
                {p.egzamin_sluzba_przygotowawcza === "zaliczony"
                  ? "egzamin ze służby przygotowawczej zaliczony"
                  : p.egzamin_sluzba_przygotowawcza === "brak"
                    ? "egzamin ze służby przygotowawczej jeszcze niezdany"
                    : "służba przygotowawcza nie dotyczy"}
              </span>
            </p>
          )}
        </div>
      )}
      {biezace.length > 0 && (
        <>
          <span className="kafel-etykieta">Bieżąca ocena, skala 1–{max} pkt</span>
          <ul className="slupki">
            {biezace.map((k) => (
              <li key={k.kompetencja_id}>
                <span className="nazwa-slupka">{nazwaKryterium(k.nazwa)}</span>
                <span className="tor" title={`${nazwaKryterium(k.nazwa)}: ${k.decyzja!.punkty} z ${max} pkt`}>
                  <span className="wypelnienie" style={{ width: `${(k.decyzja!.punkty / max) * 100}%` }} />
                </span>
                <strong className="wartosc-slupka">{k.decyzja!.punkty}</strong>
              </li>
            ))}
          </ul>
        </>
      )}
      {poprzednieSlupki && (
        <>
          <span className="kafel-etykieta">Poprzednia ocena, skala 1–9 pkt</span>
          {poprzednieSlupki}
        </>
      )}
    </div>
  );
}

/** Opis stanowiska widoczny, ale skrócony: cel i zadania dominujące w 2 liniach; reszta po „Cały opis stanowiska”. */
function OpisStanowiska({ osp }: { osp: NonNullable<AnalizaKroku1["osp"]> }) {
  const [caly, setCaly] = useState(false);
  return (
    <div className={`sekcja opis-stanowiska${caly ? "" : " skrocone"}`}>
      <h2>Opis stanowiska</h2>
      <span className="kafel-etykieta">Cel stanowiska</span>
      <p className="zero cel-stanowiska">{osp.cel.tekst}</p>
      <span className="kafel-etykieta">Zadania dominujące</span>
      <ol className="zadania-karty">
        {osp.zadania_dominujace.map((z) => (
          <li key={z.nr}>
            <span className="tekst-zadania">{z.tekst}</span>
          </li>
        ))}
      </ol>
      {caly && osp.kompetencje_miekkie.lista.length > 0 && (
        <>
          <span className="kafel-etykieta">Kompetencje miękkie z opisu</span>
          <div className="etykiety">
            {osp.kompetencje_miekkie.lista.map((k) => (
              <span key={k} className="znacznik">
                {k}
              </span>
            ))}
          </div>
        </>
      )}
      <button type="button" className="link" aria-expanded={caly} onClick={() => setCaly(!caly)}>
        {caly ? "Zwiń opis stanowiska" : "Cały opis stanowiska"}
      </button>
    </div>
  );
}

/** Przycisk nazwany czynnością według etapu (#25): w okresie oceny bez przycisku oceny. */
function NastepnyKrok({
  dane,
  prowadzi,
  onOcen,
  przelozony,
  hr,
  onZobacz,
}: {
  dane: Dane;
  prowadzi: boolean;
  onOcen: () => void;
  przelozony: Pracownik | null;
  hr: boolean;
  onZobacz: () => void;
}) {
  const c = dane.cykl;
  const p = dane.proces;
  // Po zakończonej pierwszej ocenie nie ma kolejnej pierwszej (API: 409); dalej decyzja kadrowa (icc-30, PR 123).
  if (p?.sciezka === "pierwsza" && p.status === "ZAKONCZONY") {
    return (
      <div className="ramka nastepny">
        <span className="kafel-etykieta">Następny krok</span>
        <strong>Pierwsza ocena zakończona</strong>
        <span className="termin">Dalej decyzja kadrowa o dalszym zatrudnieniu.</span>
        {!hr && (
          <button type="button" className="jasny" onClick={onZobacz}>
            Zobacz ocenę
          </button>
        )}
      </div>
    );
  }
  // Karol 22.11: „dlaczego mnie od razu nie przerzuciło? A, bo jest w toku” – ocena w toku mówi wprost, gdzie jest.
  const wToku = p ? miejsceWToku(p, c) : null;
  const tytul = wToku ? `W toku: ${wToku.opis}` : c?.czynnosc ?? (p ? "Ocena w toku" : "Ustal ścieżkę oceny");
  const przycisk = wToku
    ? `Kontynuuj: ${wToku.ekran}`
    : !c
      ? p
        ? "Kontynuuj ocenę"
        : "Rozpocznij ocenę"
      : c.etap === "kryteria"
        ? "Rozpocznij ocenę"
        : c.etap === "ocena"
          ? "Zakończ ocenę"
          : null;
  const pierwsza = (c?.sciezka ?? p?.sciezka) === "pierwsza";
  return (
    <div className="ramka nastepny">
      <span className="kafel-etykieta">Następny krok</span>
      <strong>{tytul}</strong>
      {c?.termin && (
        <span className={c.po_terminie ? "termin zagrozony" : "termin"}>
          {wToku ? `${c.termin.nazwa} do` : "Termin:"} {data(c.termin.data)}
          {c.dni_do_terminu !== null && <> ({kiedy(c.dni_do_terminu)})</>}
        </span>
      )}
      {c?.etap === "okres" && !wToku && (
        <span className="termin">
          {pierwsza ? "Rozmowa wstępna odbyta. Pierwszą ocenę zaczniesz bliżej terminu." : "Część I zakończona. Ocenę zakończysz bliżej terminu."}
        </span>
      )}
      {prowadzi && przycisk && (
        <button type="button" onClick={onOcen}>
          {przycisk}
        </button>
      )}
      {!prowadzi && (
        <span className="termin">
          Prowadzi przełożony{przelozony ? `: ${przelozony.imie} ${przelozony.nazwisko}` : ""}.
        </span>
      )}
      {/* HR nie wchodzi w treść oceny; pracownik ogląda ją po zakończeniu (przegląd serwera, zgłoszenie 122, poz. 1). */}
      {!prowadzi && p && !hr && p.status !== "W_TOKU" && (
        <button type="button" className="jasny" onClick={onZobacz}>
          Zobacz ocenę
        </button>
      )}
    </div>
  );
}

/** Gdzie stoi ocena w toku, którą trzeba dokończyć (null: nic do zrobienia teraz, np. okres oceny po części I). */
function miejsceWToku(p: ProcesOceny, c: EtapOsoby | null): { opis: string; ekran: string } | null {
  if (p.status !== "W_TOKU") return null;
  const pierwsza = p.sciezka === "pierwsza";
  if (p.krok >= 6) return { opis: pierwsza ? "pierwsza ocena na piśmie" : "zakończenie oceny, ocena na piśmie", ekran: "ocena na piśmie" };
  if (p.krok >= 3) return { opis: pierwsza ? "pierwsza ocena, rozmowa oceniająca" : "zakończenie oceny, rozmowa oceniająca", ekran: "rozmowa oceniająca" };
  // Pierwsza ocena: rozpoczęcie kończy zapis rozmowy wstępnej (cykl wychodzi z etapu „kryteria”), nie data zapoznania (#99).
  if (pierwsza && c && c.etap !== "kryteria") return null;
  if (!p.krok2?.zapoznanie)
    return pierwsza
      ? { opis: "rozpoczęcie, rozmowa wstępna", ekran: "rozmowa wstępna" }
      : { opis: "rozpoczęcie oceny, kryteria i część I", ekran: "kryteria i wskaźniki" };
  return null;
}

/** Konto pracownika: zamiast „Następnego kroku” procesu — własna samoocena (#9). */
function NastepnySamoocena({ s, onOtworz }: { s: Samoocena; onOtworz: () => void }) {
  const tytul =
    s.status === "przekazana"
      ? `Samoocena przekazana ${s.przekazano ? data(s.przekazano) : ""}`
      : s.status === "szkic"
        ? `Samoocena: odpowiedzi ${s.wypelniono} z ${s.wybrano}`
        : "Wypełnij samoocenę";
  return (
    <div className="ramka nastepny">
      <span className="kafel-etykieta">Następny krok</span>
      <strong>{tytul}</strong>
      <span className="termin">Samoocena nie zmienia oceny. Przełożony omówi ją z Tobą na rozmowie.</span>
      <button type="button" onClick={onOtworz}>
        {s.status === "przekazana" ? "Zobacz samoocenę" : s.status === "szkic" ? "Dokończ samoocenę" : "Rozpocznij samoocenę"}
      </button>
    </div>
  );
}

/** Przełożony: status samooceny i rozbieżności (≥ 4 pkt) z podstawą; HR i pracownik nie dostają tych pól. */
function LiniaSamooceny({ ocena }: { ocena: StanOceny | null }) {
  const st = ocena?.samoocena_status;
  if (!ocena || !st) return null;
  if (st !== "przekazana") return null;
  const rozbiezne = ocena.kryteria.flatMap((k) => k.wskazniki).filter((x) => x.rozbieznosc).length;
  // Karol 22.11: rozbieżności „muszą być jasno” – jedna liczba do omówienia, bez metatekstu.
  return (
    <p className={`linia-samooceny${rozbiezne ? " do-omowienia" : ""}`}>
      {rozbiezne ? (
        <>
          Samoocena: <strong>{rozbiezne} {rozbiezne === 1 ? "wskaźnik" : rozbiezne < 5 ? "wskaźniki" : "wskaźników"} do omówienia</strong> na rozmowie
          (różnica co najmniej 4 pkt)
        </>
      ) : (
        "Samoocena przekazana, bez rozbieżności do omówienia."
      )}
    </p>
  );
}
