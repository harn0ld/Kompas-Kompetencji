import { Fragment, useEffect, useState } from "react";
import { nazwaKryterium } from "./Kompetencje";
import {
  pobierzCykl,
  pobierzKrok1,
  pobierzMapeKompetencji,
  pobierzPracownikow,
  pobierzProcesy,
  pobierzTerminy,
  type EtapOsoby,
  type MapaKompetencji as Mapa,
  type Pracownik,
} from "./api";
import type { Sesja } from "./Konto";
import { SzkieletListy } from "./Lista";
import { Ikona } from "./Ikona";
import { OsTerminow, type PunktOsi } from "./Wykresy";
import {
  data,
  kiedy,
  nastepnyKrok,
  odmiana,
  osoby,
  podzial,
  poTerminie,
  wkrotce,
  doZrobienia,
  wedlugKomorek,
  NAZWA_ETAPU,
  NAZWA_SCIEZKI,
  type FiltrPracownikow,
  type Sprawa,
} from "./zespol-dane";
import "./widoki.css";
import "./zespol.css";

/**
 * Sprawy osób w zakresie użytkownika: przełożony podwładnych, HR wszystkich, oceniany siebie.
 * Proces w toku i termin z API; dla osób bez procesu ścieżka proponowana z analizy kroku 1.
 */
export function useSprawy(sesja: Sesja, onWyloguj: () => void) {
  const [sprawy, setSprawy] = useState<Sprawa[] | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    let aktualne = true;
    (async () => {
      try {
        const [ludzie, procesy, terminy, cykl] = await Promise.all([
          pobierzPracownikow(sesja.token),
          pobierzProcesy(sesja.token),
          // Brak terminów albo etapów nie blokuje widoku; liczby powiedzą wtedy, czego nie wiadomo.
          pobierzTerminy(sesja.token).catch(() => []),
          pobierzCykl(sesja.token).catch(() => []),
        ]);
        const wynik = await Promise.all(
          ludzie.map(async (osoba): Promise<Sprawa> => {
            const proces = procesy.find((p) => p.osoba_id === osoba.osoba_id && p.status === "W_TOKU") ?? null;
            const termin = (proces && terminy.find((t) => t.proces_id === proces.id)) || null;
            const c = cykl.find((x) => x.osoba_id === osoba.osoba_id) ?? null;
            if (proces) return { osoba, proces, proponowana: proces.sciezka, termin, cykl: c };
            // Ścieżkę podaje /api/cykl; analiza kroku 1 tylko wtedy, gdy etapu brak.
            if (c) return { osoba, proces: null, proponowana: c.sciezka, termin: null, cykl: c };
            const analiza = await pobierzKrok1(sesja.token, osoba.osoba_id).catch(() => null);
            return { osoba, proces: null, proponowana: analiza?.sciezka.proponowana ?? null, termin: null, cykl: null };
          }),
        );
        // Najpierw najbliższy termin z cyklu (po terminie na górze), osoby bez terminu na końcu.
        const dniDo = (s: Sprawa) => s.cykl?.dni_do_terminu ?? s.termin?.dni_do_terminu ?? 99999;
        wynik.sort((a, b) => dniDo(a) - dniDo(b));
        if (aktualne) setSprawy(wynik);
      } catch (err) {
        if (String(err).includes("401")) onWyloguj();
        else if (aktualne) setBlad("Nie udało się pobrać danych zespołu.");
      }
    })();
    return () => {
      aktualne = false;
    };
  }, [sesja.token, onWyloguj]);

  return { sprawy, blad };
}

/** Wybrana komórka: cały zakres (urząd albo zespół przełożonego), departament albo wydział. */
interface Wybor {
  departament?: string;
  wydzial?: string;
}

const komorkaWyboru = (w: Wybor) => (w.wydzial ? `${w.departament} / ${w.wydzial}` : w.departament);

function wZakresie(s: Sprawa, w: Wybor): boolean {
  const { departament, wydzial } = podzial(s.osoba.komorka);
  return (!w.departament || departament === w.departament) && (!w.wydzial || wydzial === w.wydzial);
}

const ETAPY: EtapOsoby["etap"][] = ["kryteria", "okres", "ocena", "brak_danych"];
/** Zasięg osi terminów w dniach. */
const HORYZONT = 90;

function policz(lista: Sprawa[]) {
  return {
    osob: lista.length,
    etapy: Object.fromEntries(ETAPY.map((e) => [e, lista.filter((s) => s.cykl?.etap === e).length])) as Record<EtapOsoby["etap"], number>,
    poTerminie: lista.filter(poTerminie),
    wkrotce: lista.filter(wkrotce),
    teraz: lista.filter(doZrobienia),
    pozytywne: lista.filter((s) => s.osoba.ostatnia_ocena_okresowa?.wynik === "pozytywna").length,
    negatywne: lista.filter((s) => s.osoba.ostatnia_ocena_okresowa?.wynik === "negatywna").length,
    bezOceny: lista.filter((s) => !s.osoba.ostatnia_ocena_okresowa).length,
  };
}

const kto = (s: Sprawa) => `${s.osoba.imie} ${s.osoba.nazwisko}`;

/** Pole CSV: tekst zaczynający się od =, +, -, @ dostaje apostrof (Excel nie wykona go jako formuły). */
function poleCsv(v: string | number): string {
  if (typeof v === "number") return String(v);
  const t = /^[=+\-@\t\r]/.test(v) ? `'${v}` : v;
  return /[;"\r\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
}

/** Zestawienie osób w zakresie; dla przełożonego punkty kryteriów z mapy kompetencji. Separator „;”, BOM dla Excela. */
function zestawienieCsv(lista: Sprawa[], mapa: Mapa | null): string {
  const punkty = (s: Sprawa) => mapa?.osoby.find((o) => o.osoba_id === s.osoba.osoba_id)?.punkty ?? {};
  const kryteria = (mapa?.kryteria ?? []).filter((k) => lista.some((s) => punkty(s)[k.kompetencja_id] !== undefined));
  const naglowek = ["osoba", "stanowisko", "departament", "wydział", "ścieżka", "czynność", "termin", "dni do terminu", "ostatnia ocena"];
  const wiersze = lista.map((s) => {
    const { departament, wydzial } = podzial(s.osoba.komorka);
    const sciezka = s.cykl?.sciezka ?? s.proponowana;
    const ocena = s.osoba.ostatnia_ocena_okresowa;
    return [
      kto(s),
      s.osoba.stanowisko,
      departament,
      wydzial,
      sciezka ? NAZWA_SCIEZKI[sciezka] : "",
      s.cykl?.czynnosc ?? nastepnyKrok(s),
      s.cykl?.termin ? data(s.cykl.termin.data) : "",
      s.cykl?.dni_do_terminu ?? "",
      ocena ? `${ocena.wynik}, ${data(ocena.data)}` : "brak",
      ...kryteria.map((k) => punkty(s)[k.kompetencja_id] ?? ""),
    ];
  });
  const tabela = [[...naglowek, ...kryteria.map((k) => nazwaKryterium(k.nazwa))], ...wiersze];
  return "\uFEFF" + tabela.map((w) => w.map(poleCsv).join(";")).join("\r\n") + "\r\n";
}

function pobierzPlik(nazwa: string, tresc: string) {
  const url = URL.createObjectURL(new Blob([tresc], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nazwa;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); // Firefox i Safari czytają adres po kliknięciu
}

const departamenty = (n: number) => `${n} ${odmiana(n, "departament", "departamenty", "departamentów")}`;
const wydzialy = (n: number) => `${n} ${odmiana(n, "wydział", "wydziały", "wydziałów")}`;
const poNazwisku = (a: Sprawa, b: Sprawa) =>
  a.osoba.nazwisko.localeCompare(b.osoba.nazwisko, "pl") || a.osoba.imie.localeCompare(b.osoba.imie, "pl");

/** Etap i termin osoby w jednej krótkiej plakietce: „Rozmowa oceniająca · 02.12.2026” albo „… · 3 dni po terminie”. */
function plakietka(s: Sprawa): string {
  const c = s.cykl;
  if (!c) return nastepnyKrok(s);
  if (!c.termin) return c.czynnosc;
  const kiedyTxt = c.po_terminie && c.dni_do_terminu !== null ? kiedy(c.dni_do_terminu) : data(c.termin.data);
  return `${c.czynnosc} · ${kiedyTxt}`;
}

/** Punkty kompetencji: ton komórki względem poziomu oczekiwań, średnia z przecinkiem. */
const tonPunktow = (pkt: number, oczekiwany: number) => (pkt < oczekiwany ? "ponizej" : pkt > oczekiwany ? "powyzej" : "");
const liczba = (x: number) => x.toFixed(1).replace(".", ",");
const srednia = (w: number[]) => Math.round((w.reduce((a, b) => a + b, 0) / w.length) * 10) / 10;

/** Krótkie nagłówki kryteriów do tabeli (pełna nazwa w `title`); nieznane kryterium dostaje pełną nazwę. */
const KROTKO: Record<string, string> = {
  rzetelnosc: "Rzetelność",
  komunikacja: "Komunikacja",
  "wykorzystywanie-wiedzy-i-doskonalenie-zawodowe": "Wiedza i doskonalenie",
  "organizacja-pracy-i-orientacja-na-osiaganie-celow": "Organizacja pracy",
  wspolpraca: "Współpraca",
  "zarzadzanie-ludzmi": "Zarządzanie ludźmi",
  "podejmowanie-decyzji-i-odpowiedzialnosc": "Decyzje i odpowie­dzialność",
};

/**
 * Kompetencje osób w zakresie (tylko przełożony): dwa wnioski, tabela osoby × kryteria ze średnią zespołu w pierwszym
 * wierszu. Kolejność według struktury i nazwiska, nigdy według wyniku. Kolor tła tylko poniżej i powyżej oczekiwań.
 */
function Kompetencje({ mapa, sprawy, onWybierz }: { mapa: Mapa; sprawy: Sprawa[]; onWybierz?: (p: Pracownik) => void }) {
  const oczek = mapa.poziom_oczekiwan;
  const poId = new Map(mapa.osoby.map((o) => [o.osoba_id, o]));
  const kolejnosc = [...sprawy].sort((a, b) => a.osoba.komorka.localeCompare(b.osoba.komorka, "pl") || poNazwisku(a, b));
  const wiersze = kolejnosc.flatMap((s) => {
    const o = poId.get(s.osoba.osoba_id);
    return o ? [{ s, o }] : [];
  });
  const bez = kolejnosc.filter((s) => !poId.has(s.osoba.osoba_id));
  const kryteria = mapa.kryteria.filter((k) => wiersze.some(({ o }) => o.punkty[k.kompetencja_id] !== undefined));
  const staty = kryteria.map((k) => {
    const w = wiersze.map(({ o }) => o.punkty[k.kompetencja_id]).filter((x): x is number => x !== undefined);
    return { k, n: w.length, sr: srednia(w), ponizej: w.filter((x) => x < oczek).length };
  });
  // Do rozwoju: najwięcej osób poniżej oczekiwań (co najmniej dwie). Mocna strona: najwyższa średnia powyżej
  // oczekiwań u co najmniej dwóch osób (jedna osoba to nie zespół).
  const slabe = [...staty].sort((a, b) => b.ponizej - a.ponizej || a.sr - b.sr).find((x) => x.ponizej >= 2);
  const mocne = staty.filter((x) => x.n >= 2 && x.sr > oczek).sort((a, b) => b.sr - a.sr)[0];
  const rozbieznosci = wiersze.some(({ o }) => o.rozbieznosci !== null);
  const [min, max] = [Math.min(...mapa.skala), Math.max(...mapa.skala)];
  const zrodlo = (o: Mapa["osoby"][number]) =>
    o.zrodlo === "biezaca_ocena" ? "ocena bieżąca" : `ocena ${o.data ? `${o.data.slice(5, 7)}.${o.data.slice(0, 4)}` : "z akt"}`;
  const osoba = (p: Pracownik) =>
    onWybierz ? (
      <button type="button" className="link" onClick={() => onWybierz(p)}>
        {p.imie} {p.nazwisko}
      </button>
    ) : (
      `${p.imie} ${p.nazwisko}`
    );

  return (
    <section className="sekcja-zespolu">
      <h2>Kompetencje</h2>
      {wiersze.length === 0 ? (
        <p className="meta">Nikt w tym zakresie nie ma jeszcze punktów za kryteria.</p>
      ) : (
        <>
          {(slabe || mocne) && (
            <div className="wnioski-mapy">
              {slabe && (
                <p className="wniosek do-rozwoju">
                  <span className="kafel-etykieta">Do rozwoju w zespole</span>
                  <strong>{nazwaKryterium(slabe.k.nazwa)}</strong>
                  <span>
                    {slabe.ponizej} z {slabe.n} osób poniżej oczekiwań, średnio {liczba(slabe.sr)} pkt
                  </span>
                </p>
              )}
              {mocne && (
                <p className="wniosek mocna">
                  <span className="kafel-etykieta">Mocna strona zespołu</span>
                  <strong>{nazwaKryterium(mocne.k.nazwa)}</strong>
                  <span>
                    średnio {liczba(mocne.sr)} pkt ({osoby(mocne.n)})
                  </span>
                </p>
              )}
            </div>
          )}
          <div className="tabela-kompetencji" role="region" aria-label="Kompetencje: osoby i kryteria" tabIndex={0}>
            <table>
              <colgroup>
                <col className="kol-osoby" />
                {kryteria.map((k) => (
                  <col key={k.kompetencja_id} />
                ))}
                {rozbieznosci && <col />}
              </colgroup>
              <thead>
                <tr>
                  <th scope="col">Osoba</th>
                  {kryteria.map((k) => (
                    <th key={k.kompetencja_id} scope="col" title={nazwaKryterium(k.nazwa)}>
                      <span className="naglowek-kryterium">{KROTKO[k.kompetencja_id] ?? nazwaKryterium(k.nazwa)}</span>
                    </th>
                  ))}
                  {rozbieznosci && (
                    <th scope="col">
                      <span className="naglowek-kryterium">Samoocena do omówienia</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                <tr className="srednia">
                  <th scope="row">Średnia zespołu</th>
                  {staty.map((x) => (
                    <td key={x.k.kompetencja_id}>
                      <strong className={tonPunktow(x.sr, oczek)}>{liczba(x.sr)}</strong>
                      <span className="meta">{osoby(x.n)}</span>
                    </td>
                  ))}
                  {rozbieznosci && <td />}
                </tr>
                {wiersze.map(({ s, o }) => (
                  <tr key={o.osoba_id}>
                    <th scope="row">
                      {osoba(s.osoba)}
                      <span className="meta">{zrodlo(o)}</span>
                    </th>
                    {kryteria.map((k) => {
                      const v = o.punkty[k.kompetencja_id];
                      return v === undefined ? (
                        <td key={k.kompetencja_id} className="poza-arkuszem" title="kryterium spoza arkusza tej osoby">
                          –
                        </td>
                      ) : (
                        <td key={k.kompetencja_id} className={tonPunktow(v, oczek)}>
                          {v}
                        </td>
                      );
                    })}
                    {rozbieznosci && <td className={o.rozbieznosci === null ? "poza-arkuszem" : undefined}>{o.rozbieznosci ?? "–"}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {bez.length > 0 && (
            <p className="meta bez-punktow">
              Bez punktów za kryteria:{" "}
              {bez.map((s, i) => (
                <Fragment key={s.osoba.osoba_id}>
                  {i > 0 && ", "}
                  {osoba(s.osoba)}
                </Fragment>
              ))}
            </p>
          )}
        </>
      )}
      <p className="meta podstawa-kompetencji">
        <span className="probka ponizej" aria-hidden="true" /> poniżej oczekiwań
        <span className="probka powyzej" aria-hidden="true" /> powyżej · skala {min}–{max} pkt, poziom oczekiwań {oczek} · źródło: ostatnia
        ocena okresowa z akt albo ocena bieżąca
      </p>
    </section>
  );
}

/**
 * Zespół: struktura zespołu i analiza per komórka. Klik departamentu albo wydziału zawęża całą stronę (liczby, oś,
 * kompetencje, ostatnie oceny, CSV); okruszek cofa zakres. Klik liczby otwiera listę Pracownicy z filtrem.
 */
export function Zespol({
  sesja,
  onPracownicy,
  onWyloguj,
  onWybierz,
}: {
  sesja: Sesja;
  onPracownicy: (f: FiltrPracownikow) => void;
  onWyloguj: () => void;
  onWybierz?: (p: Pracownik) => void;
}) {
  const { sprawy, blad } = useSprawy(sesja, onWyloguj);
  const [wybor, ustawWybor] = useState<Wybor>({});
  // Zgłoszenie 189: „Wróć” jak na karcie pracownika – wraca do zakresu, z którego otwarto bieżący
  // (wydział otwarty z departamentu wraca do departamentu, otwarty z „Całego zespołu” – do całości).
  const [historia, setHistoria] = useState<Wybor[]>([]);
  const setWybor = (nowy: Wybor) => {
    setHistoria((h) => [...h, wybor]);
    ustawWybor(nowy);
  };
  const wroc = () => {
    ustawWybor(historia[historia.length - 1] ?? {});
    setHistoria((h) => h.slice(0, -1));
  };
  // Mapa kompetencji (#33) tylko dla przełożonego: HR nie ma prawa do treści ocen (zadanie MC, minimalizacja danych).
  const [mapa, setMapa] = useState<Mapa | null>(null);
  const przelozony = sesja.uzytkownik.rola === "przelozony";
  useEffect(() => {
    if (przelozony) pobierzMapeKompetencji(sesja.token).then(setMapa).catch(() => setMapa(null));
  }, [sesja.token, przelozony]);
  const korzen = sesja.uzytkownik.rola === "hr" ? "Cały urząd" : "Cały zespół";

  if (blad) return <p className="blad">{blad}</p>;
  if (!sprawy)
    return (
      <div className="widok">
        <h1>Zespół</h1>
        <SzkieletListy wiersze={3} />
      </div>
    );

  const zakres = sprawy.filter((s) => wZakresie(s, wybor));
  const l = policz(zakres);
  const komorka = komorkaWyboru(wybor);
  const doListy = (f: FiltrPracownikow = {}) => () => onPracownicy({ komorka, ...f });

  // Drzewo departament → wydział → osoby; wydział równy departamentowi (komórka bez wydziału) nie ma własnego wiersza.
  const grupy = wedlugKomorek(zakres, (s) => s.osoba.komorka);
  const ileWydzialow = grupy.reduce((a, g) => a + g.wydzialy.filter((w) => w.wydzial !== g.departament).length, 0);
  const linijkaZakresu = [
    osoby(l.osob),
    !wybor.departament && departamenty(grupy.length),
    !wybor.wydzial && ileWydzialow > 0 && wydzialy(ileWydzialow),
  ]
    .filter(Boolean)
    .join(" · ");

  const zTerminem = zakres.filter((s) => s.cykl?.termin && s.cykl.dni_do_terminu !== null);
  const punkty: PunktOsi[] = zTerminem.map((s) => {
    const c = s.cykl!;
    const dni = c.dni_do_terminu!;
    return {
      klucz: s.osoba.osoba_id,
      znak: `${s.osoba.imie.charAt(0)}${s.osoba.nazwisko.charAt(0)}`,
      tytul: kto(s),
      opis: `${c.czynnosc}, ${data(c.termin!.data)} (${kiedy(dni)}) · ${NAZWA_ETAPU[c.etap]}`,
      dni,
      ton: c.etap,
      onClick: onWybierz ? () => onWybierz(s.osoba) : undefined,
    };
  });
  const pozniej = punkty.filter((p) => p.dni > HORYZONT).length;
  const bezTerminu = l.osob - zTerminem.length;

  const liczby: { etykieta: string; n: number; ton?: "zle" | "uwaga"; onClick: () => void }[] = [
    { etykieta: "Po terminie", n: l.poTerminie.length, ton: "zle", onClick: doListy({ termin: "po_terminie" }) },
    { etykieta: "Termin w ciągu 14 dni", n: l.wkrotce.length, ton: "uwaga", onClick: doListy({ termin: "wkrotce" }) },
    { etykieta: "Do zrobienia teraz", n: l.teraz.length, onClick: doListy() },
  ];
  const oceny: { tekst: string; n: number; filtr: FiltrPracownikow["ocena"] }[] = [
    { tekst: odmiana(l.pozytywne, "pozytywna", "pozytywne", "pozytywnych"), n: l.pozytywne, filtr: "pozytywna" },
    { tekst: odmiana(l.negatywne, "negatywna", "negatywne", "negatywnych"), n: l.negatywne, filtr: "negatywna" },
    { tekst: "bez oceny", n: l.bezOceny, filtr: "brak" },
  ];

  return (
    <div className="widok zespol">
      <div className="naglowek-widoku">
        {wybor.departament && (
          <button type="button" className="link wstecz" onClick={wroc}>
            <Ikona nazwa="wstecz" rozmiar={20} />
            Wróć
          </button>
        )}
        <div className="wiersz-tytulu">
          <h1>Zespół</h1>
          <button
            type="button"
            className="link pobierz-csv"
            onClick={() => pobierzPlik(`zestawienie-zespolu-${new Date().toISOString().slice(0, 10)}.csv`, zestawienieCsv(zakres, mapa))}
          >
            Pobierz zestawienie (CSV)
          </button>
        </div>
        {wybor.departament && (
          <nav className="okruszki" aria-label="Zakres">
            <button type="button" className="link" onClick={() => setWybor({})}>
              {korzen}
            </button>
            <Ikona nazwa="dalej" rozmiar={16} />
            {wybor.wydzial ? (
              <button type="button" className="link" onClick={() => setWybor({ departament: wybor.departament })}>
                {wybor.departament}
              </button>
            ) : (
              <span aria-current="page">{wybor.departament}</span>
            )}
            {wybor.wydzial && (
              <>
                <Ikona nazwa="dalej" rozmiar={16} />
                <span aria-current="page">{wybor.wydzial}</span>
              </>
            )}
          </nav>
        )}
        <p className="meta linijka-zakresu">{linijkaZakresu}</p>
      </div>

      <div className="liczby-zespolu">
        {liczby.map((x) => {
          const tresc = (
            <>
              <strong className={x.n ? x.ton : undefined}>{x.n}</strong>
              <span>{x.etykieta}</span>
            </>
          );
          return x.n ? (
            <button key={x.etykieta} type="button" className="liczba-zespolu" onClick={x.onClick}>
              {tresc}
            </button>
          ) : (
            <div key={x.etykieta} className="liczba-zespolu">
              {tresc}
            </div>
          );
        })}
      </div>

      <section className="sekcja-zespolu">
        <h2>Struktura</h2>
        <table className="struktura">
          <thead>
            <tr>
              <th scope="col">Osoba</th>
              <th scope="col">Stanowisko</th>
              <th scope="col">Etap i termin</th>
              <th scope="col">Ostatnia ocena</th>
            </tr>
          </thead>
          {grupy.map((g) => (
            <tbody key={g.departament}>
              {!wybor.departament && (
                <tr className="wiersz-departamentu">
                  <th colSpan={4} scope="colgroup">
                    <button type="button" className="zakres" onClick={() => setWybor({ departament: g.departament })}>
                      <span className="nazwa-zakresu">{g.departament}</span>
                      <span className="liczba-zakresu">{osoby(g.wydzialy.reduce((a, w) => a + w.ludzie.length, 0))}</span>
                      <Ikona nazwa="dalej" rozmiar={16} />
                    </button>
                  </th>
                </tr>
              )}
              {g.wydzialy.map((w) => (
                <Fragment key={w.wydzial}>
                  {!wybor.wydzial && w.wydzial !== g.departament && (
                    <tr className="wiersz-wydzialu">
                      <th colSpan={4} scope="colgroup">
                        <button
                          type="button"
                          className="zakres"
                          onClick={() => setWybor({ departament: g.departament, wydzial: w.wydzial })}
                        >
                          <span className="nazwa-zakresu">{w.wydzial}</span>
                          <span className="liczba-zakresu">{osoby(w.ludzie.length)}</span>
                          <Ikona nazwa="dalej" rozmiar={16} />
                        </button>
                      </th>
                    </tr>
                  )}
                  {[...w.ludzie].sort(poNazwisku).map((s) => {
                    const ocena = s.osoba.ostatnia_ocena_okresowa;
                    return (
                      <tr key={s.osoba.osoba_id} className="wiersz-osoby">
                        <th scope="row">
                          {onWybierz ? (
                            <button type="button" className="link" onClick={() => onWybierz(s.osoba)}>
                              {kto(s)}
                            </button>
                          ) : (
                            kto(s)
                          )}
                        </th>
                        <td>{s.osoba.stanowisko}</td>
                        <td>
                          <span className={poTerminie(s) ? "plakietka po-terminie" : "plakietka"}>{plakietka(s)}</span>
                        </td>
                        <td>
                          {ocena ? (
                            <>
                              <span className={ocena.wynik === "negatywna" ? "negatywna" : undefined}>{ocena.wynik}</span>
                              <span className="data-oceny"> · {data(ocena.data)}</span>
                            </>
                          ) : (
                            <span className="bez-oceny">bez oceny</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </Fragment>
              ))}
            </tbody>
          ))}
        </table>
        <p className="linia-ocen">
          Ostatnie oceny:{" "}
          {oceny.map((o, i) => (
            <Fragment key={o.filtr}>
              {i > 0 && " · "}
              {o.n ? (
                <button type="button" className="pozycja-legendy" onClick={doListy({ ocena: o.filtr })}>
                  <strong>{o.n}</strong> {o.tekst}
                </button>
              ) : (
                <span>
                  <strong>{o.n}</strong> {o.tekst}
                </span>
              )}
            </Fragment>
          ))}
        </p>
      </section>

      <section className="sekcja-zespolu">
        <div className="wiersz-tytulu">
          <h2>Terminy w najbliższych {HORYZONT} dniach</h2>
          <ul className="legenda" aria-label="Etapy">
            {ETAPY.filter((e) => l.etapy[e] > 0).map((e) => (
              <li key={e}>
                <button type="button" className="pozycja-legendy" onClick={doListy({ etap: e })}>
                  <span className={`kropka ${e}`} aria-hidden="true" />
                  {NAZWA_ETAPU[e]} <strong>{l.etapy[e]}</strong>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <OsTerminow punkty={punkty} horyzont={HORYZONT} />
        {(pozniej > 0 || bezTerminu > 0) && (
          <p className="meta">
            {[pozniej > 0 && `Później niż za ${HORYZONT} dni: ${osoby(pozniej)}`, bezTerminu > 0 && `bez terminu: ${osoby(bezTerminu)}`]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
      </section>

      {mapa && <Kompetencje mapa={mapa} sprawy={zakres} onWybierz={onWybierz} />}
    </div>
  );
}
