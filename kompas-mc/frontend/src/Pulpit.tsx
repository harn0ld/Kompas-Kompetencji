import { FormEvent, useEffect, useMemo, useState } from "react";
import AsystentFormalny from "./AsystentFormalny";
import {
  celeApi,
  pobierzCykl,
  pobierzMapeKompetencji,
  pobierzPracownikow,
  zacznijOdPoczatku,
  type Cel,
  type EtapOsoby,
  type MapaKompetencji as Mapa,
  type Pracownik,
} from "./api";
import { Ikona } from "./Ikona";
import type { Sesja } from "./Konto";
import { STATUS as STATUS_CELU } from "./CeleOsoby";
import { MapaKompetencji } from "./Kompetencje";
import { Inicjaly, SzkieletListy, WierszListy } from "./Lista";
import { Kafel } from "./Wykresy";
import { Wydra } from "./wydra/Wydra";
import { data, dni, doZrobienia, odmiana, osoby, wedlugKomorek, type FiltrPracownikow } from "./zespol-dane";
import type { Grupowanie } from "./ListaPracownikow";
import "./widoki.css";
import "./pulpit.css";

/**
 * Pulpit (strona główna) jak w makiecie v3: „Do zrobienia” to osoby z następną czynnością i terminem
 * z /api/cykl (początek okresu: kryteria albo rozmowa wstępna; koniec: rozmowa oceniająca i ocena).
 * Trzy kafle filtrują tę listę; kafla z zerem nie ma. Z prawej krótko o zespole, pod spodem mapa kompetencji
 * (przełożony). Pole na dole: jedna pasująca osoba otwiera kartę, inaczej pulpit staje się rozmową
 * z asystentem na całym ekranie. Frontend niczego nie liczy z przepisów.
 */
const DZIS = new Date().toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" });

const NA_START = 5;

type Filtr = "wszystkie" | "po_terminie" | "kryteria" | "ocena";
const NAZWA_FILTRA: Record<Exclude<Filtr, "wszystkie">, string> = {
  po_terminie: "po terminie",
  kryteria: "do rozpoczęcia",
  ocena: "do zakończenia",
};

interface Sprawa {
  osoba: Pracownik;
  cykl: EtapOsoby;
}

const pasuje = (s: Sprawa, f: Filtr) => f === "wszystkie" || (f === "po_terminie" ? s.cykl.po_terminie : s.cykl.etap === f);

/** Czynność w wierszu: przełożony widzi swoją czynność z /api/cykl, pracownik to, co go czeka (rozmowa z przełożonym). */
function opisCzynnosci(e: EtapOsoby, zespol: boolean): string {
  const czynnosc = zespol
    ? e.czynnosc
    : e.etap === "kryteria"
      ? "Rozmowa z przełożonym o kryteriach"
      : e.etap === "ocena"
        ? "Rozmowa z przełożonym"
        : e.czynnosc;
  return e.termin ? `${czynnosc} · do ${data(e.termin.data)}` : czynnosc;
}

/** „po terminie 2 dni” na czerwono, „za 5 dni” na bursztynowo do 14 dni; dalsze terminy bez plakietki. */
function Plakietka({ e }: { e: EtapOsoby }) {
  const n = e.dni_do_terminu;
  if (n === null) return null;
  if (e.po_terminie) return <span className="status negatywna">po terminie {dni(-n)}</span>;
  if (n === 0) return <span className="status uwaga">dziś</span>;
  if (n <= 14) return <span className="status uwaga">za {dni(n)}</span>;
  return null;
}

export function Pulpit({
  sesja,
  onWybierz,
  onWyloguj,
  onZespol,
  onPracownicy,
  onCele,
  onOdPoczatku,
}: {
  sesja: Sesja;
  onWybierz: (p: Pracownik) => void;
  onWyloguj: () => void;
  onZespol: () => void;
  /** Lista pracowników z filtrem albo grupowaniem (skróty z karty zespołu, zgłoszenie 187). */
  onPracownicy: (f?: FiltrPracownikow, g?: Grupowanie) => void;
  /** Konto ocenianego: przejście do „Twoje cele”. */
  onCele?: () => void;
  /** Demo (#186, #208): dane osoby skasowane, otwórz jej ocenę od pierwszego etapu. */
  onOdPoczatku: (p: Pracownik) => void;
}) {
  const [sprawy, setSprawy] = useState<Sprawa[] | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const [szukaj, setSzukaj] = useState("");
  const [filtr, setFiltr] = useState<Filtr>("wszystkie");
  const [wszystkie, setWszystkie] = useState(false);
  const [rozmowa, setRozmowa] = useState<{ id: number; tekst: string } | null>(null);
  const [mapa, setMapa] = useState<Mapa | null>(null);
  const [resetowana, setResetowana] = useState<string | null>(null);
  const [komunikat, setKomunikat] = useState<string | null>(null);
  const rola = sesja.uzytkownik.rola;
  const zespol = rola !== "oceniany";
  // Konto ocenianego (G2, 22.11): prawa kolumna z celami i ostatnią oceną zamiast pustego miejsca obok jednego wiersza.
  const [cele, setCele] = useState<Cel[] | null>(null);
  useEffect(() => {
    if (zespol || !sesja.uzytkownik.osoba_id) return;
    celeApi.lista(sesja.token, sesja.uzytkownik.osoba_id).then((l) => setCele(l.cele), () => setCele([]));
  }, [zespol, sesja.token, sesja.uzytkownik.osoba_id]);

  useEffect(() => {
    let aktualne = true;
    Promise.all([pobierzPracownikow(sesja.token), pobierzCykl(sesja.token)])
      .then(([ludzie, cykl]) => {
        const po = new Map(ludzie.map((p) => [p.osoba_id, p]));
        const wynik = cykl.filter((e) => po.has(e.osoba_id)).map((e) => ({ osoba: po.get(e.osoba_id)!, cykl: e }));
        // Najpierw po terminie, potem najbliższy termin; brak terminu na końcu.
        wynik.sort(
          (a, b) =>
            Number(b.cykl.po_terminie) - Number(a.cykl.po_terminie) ||
            (a.cykl.dni_do_terminu ?? 1e9) - (b.cykl.dni_do_terminu ?? 1e9),
        );
        if (aktualne) setSprawy(wynik);
      })
      .catch((err) => {
        if (String(err).includes("401")) onWyloguj();
        else if (aktualne) setBlad("Nie udało się pobrać spraw.");
      });
    return () => {
      aktualne = false;
    };
  }, [sesja.token, onWyloguj]);

  // Demo (#208): bez potwierdzenia; po skasowaniu danych od razu ekran „Rozpoczęcie oceny” tej osoby.
  async function odPoczatku(p: Pracownik) {
    setResetowana(p.osoba_id);
    setKomunikat(null);
    try {
      await zacznijOdPoczatku(sesja.token, p.osoba_id);
    } catch {
      setKomunikat(`Nie udało się zacząć oceny ${p.imie} ${p.nazwisko} od początku.`);
      setResetowana(null);
      return;
    }
    onOdPoczatku(p);
  }

  // Mapa kompetencji (#33) wymaga dostępu do treści ocen: ma ją przełożony, HR nie.
  useEffect(() => {
    if (rola === "przelozony") pobierzMapeKompetencji(sesja.token).then(setMapa).catch(() => setMapa(null));
  }, [sesja.token, rola]);

  const lista = useMemo(() => {
    if (!sprawy) return null;
    const q = zespol ? szukaj.trim().toLowerCase() : "";
    if (q) return sprawy.filter((s) => `${s.osoba.imie} ${s.osoba.nazwisko}`.toLowerCase().includes(q));
    return sprawy.filter((s) => doZrobienia(s) && pasuje(s, filtr));
  }, [sprawy, szukaj, filtr]);

  function wyslij(e: FormEvent) {
    e.preventDefault();
    const q = szukaj.trim();
    if (!q) return;
    // Jedna osoba pasuje do wpisu: otwórz ją; inaczej to pytanie do asystenta.
    if (zespol && lista && lista.length === 1) onWybierz(lista[0].osoba);
    else setRozmowa({ id: Date.now(), tekst: q });
    setSzukaj("");
  }

  // Bez filtra i wyszukiwania najwyżej NA_START najpilniejszych: długa lista (HR) nie chowa się pod paskiem.
  const skrocona = !wszystkie && !szukaj && filtr === "wszystkie" && (lista?.length ?? 0) > NA_START;
  const przelacz = (f: Filtr) => setFiltr((obecny) => (obecny === f ? "wszystkie" : f));
  const ile = (f: Filtr) => sprawy?.filter((s) => doZrobienia(s) && pasuje(s, f)).length ?? 0;
  const najblizszy = (f: Filtr) => sprawy?.find((s) => doZrobienia(s) && pasuje(s, f) && s.cykl.termin);
  const kafle: { f: Exclude<Filtr, "wszystkie">; etykieta: string; ton?: "zle" | "uwaga" }[] = [
    { f: "po_terminie", etykieta: "Po terminie", ton: "zle" },
    { f: "kryteria", etykieta: "Do rozpoczęcia" },
    { f: "ocena", etykieta: "Do zakończenia" },
  ];
  const ludzie = sprawy?.map((s) => s.osoba) ?? [];
  const wydzialow = sprawy ? wedlugKomorek(sprawy, (s) => s.osoba.komorka).reduce((a, g) => a + g.wydzialy.length, 0) : 0;
  const ostatnia = (w: "pozytywna" | "negatywna") => ludzie.filter((p) => p.ostatnia_ocena_okresowa?.wynik === w).length;
  const wOkresie = sprawy?.filter((s) => !doZrobienia(s)).length ?? 0;

  if (rozmowa) {
    return (
      <div className="pulpit pulpit-rozmowa">
        <div className="pulpit-rozmowa-glowa">
          <Wydra poza="stoi" szerokosc={48} naStart="machanie" />
          <div>
            <h1>Asystent formalny</h1>
            <p className="meta">Odpowiada na podstawie materiałów MC i instrukcji aplikacji. Nie ocenia pracownika.</p>
          </div>
          <button type="button" className="link" onClick={() => setRozmowa(null)}>
            Wróć do pulpitu
          </button>
        </div>
        <AsystentFormalny pytanieZZewnatrz={rozmowa} />
      </div>
    );
  }

  return (
    <div className="pulpit">
      <div className="pulpit-naglowek">
        <h1>Na dziś</h1>
        <p className="meta">{DZIS}</p>
      </div>

      {zespol && sprawy && kafle.some((k) => ile(k.f) > 0) && (
        <div className="pulpit-kafle">
          {kafle
            .filter((k) => ile(k.f) > 0)
            .map((k) => {
              const n = najblizszy(k.f);
              return (
                <Kafel
                  key={k.f}
                  etykieta={k.etykieta}
                  wartosc={osoby(ile(k.f))}
                  ton={k.ton}
                  opis={n ? `Najbliżej: ${n.osoba.imie} ${n.osoba.nazwisko}, ${n.cykl.czynnosc.toLowerCase()} do ${data(n.cykl.termin!.data)}` : ""}
                  onClick={() => przelacz(k.f)}
                  wybrany={filtr === k.f}
                />
              );
            })}
        </div>
      )}

      <div className="pulpit-kolumny">
        <section className="sekcja">
          <div className="wiersz-tytulu">
            <h2>{zespol && szukaj ? "Wyniki wyszukiwania" : rola === "oceniany" ? "Twoja ocena" : rola === "hr" ? "Terminy w urzędzie" : "Do zrobienia"}</h2>
            {filtr !== "wszystkie" && !szukaj && (
              <button type="button" className="link" onClick={() => setFiltr("wszystkie")}>
                Tylko {NAZWA_FILTRA[filtr]} · pokaż wszystko
              </button>
            )}
          </div>
          {blad && <p className="blad">{blad}</p>}
          {komunikat && <p className="blad">{komunikat}</p>}
          {!blad && lista === null && <SzkieletListy />}
          {lista?.length === 0 && (
            <p className="meta">
              {szukaj ? "Nikt nie pasuje do wpisu. Enter wyśle go jako pytanie do asystenta." : "Na dziś nic. Pozostali są w trakcie okresu oceny."}
            </p>
          )}
          {lista && lista.length > 0 && (
            <div className="lista">
              {(skrocona ? lista.slice(0, NA_START) : lista).map((s) => {
                // Demo (#186): mały przycisk w linii imienia, za plakietką terminu; wiersz nie rośnie.
                const demo = rola === "przelozony" && s.osoba.demo_od_poczatku;
                return (
                  <WierszListy
                    key={s.osoba.osoba_id}
                    lewa={<Inicjaly imie={s.osoba.imie} nazwisko={s.osoba.nazwisko} />}
                    tytul={`${s.osoba.imie} ${s.osoba.nazwisko}`}
                    znacznik={<Plakietka e={s.cykl} />}
                    akcja={
                      demo && (
                        <button
                          type="button"
                          className="pulpit-od-poczatku"
                          disabled={resetowana !== null}
                          onClick={() => odPoczatku(s.osoba)}
                        >
                          {resetowana === s.osoba.osoba_id ? "Demo: zaczynam od nowa…" : "Demo: rozpocznij od początku"}
                        </button>
                      )
                    }
                    opis={opisCzynnosci(s.cykl, zespol)}
                    onClick={() => onWybierz(s.osoba)}
                  />
                );
              })}
            </div>
          )}
          {skrocona && (
            <button type="button" className="link pulpit-wiecej" onClick={() => setWszystkie(true)}>
              Pokaż wszystkie ({lista!.length})
            </button>
          )}
          {zespol && sprawy && !szukaj && wOkresie > 0 && (
            <button type="button" className="link pulpit-wiecej" onClick={() => onPracownicy()}>
              {wOkresie} {odmiana(wOkresie, "osoba", "osoby", "osób")} w trakcie okresu oceny · wszyscy pracownicy
            </button>
          )}
        </section>

        {zespol && sprawy && (
          <aside className="pulpit-boczna">
            <section className="sekcja">
              <div className="wiersz-tytulu">
                <h2>{rola === "hr" ? "Urząd" : "Mój zespół"}</h2>
                <button type="button" className="link" onClick={onZespol}>
                  Analiza
                </button>
              </div>
              <div className="pulpit-zespol">
                <div className="pulpit-liczby">
                  {[
                    { n: ludzie.length, opis: odmiana(ludzie.length, "osoba", "osoby", "osób"), idz: () => onPracownicy() },
                    { n: wydzialow, opis: odmiana(wydzialow, "wydział", "wydziały", "wydziałów"), idz: () => onPracownicy({}, "wydzial") },
                    { n: ile("wszystkie"), opis: "do zrobienia", idz: () => onPracownicy({ doZrobienia: true }) },
                  ].map((x) => (
                    <button key={x.opis} type="button" className="pulpit-skrot" onClick={x.idz}>
                      <strong>{x.n}</strong>
                      <span>{x.opis}</span>
                    </button>
                  ))}
                </div>
                <div className="pulpit-oceny">
                  <span className="kafel-etykieta">Ostatnie oceny</span>
                  <button type="button" className="status pozytywna" onClick={() => onPracownicy({ ocena: "pozytywna" })}>
                    {ostatnia("pozytywna")} {odmiana(ostatnia("pozytywna"), "pozytywna", "pozytywne", "pozytywnych")}
                  </button>
                  {/* Zero negatywnych nie jest ostrzeżeniem: wtedy tło neutralne (zgłoszenie 221). */}
                  <button
                    type="button"
                    className={`status ${ostatnia("negatywna") > 0 ? "negatywna" : "neutralna"}`}
                    onClick={() => onPracownicy({ ocena: "negatywna" })}
                  >
                    {ostatnia("negatywna")} {odmiana(ostatnia("negatywna"), "negatywna", "negatywne", "negatywnych")}
                  </button>
                  <button type="button" className="status neutralna" onClick={() => onPracownicy({ ocena: "brak" })}>
                    {ludzie.length - ostatnia("pozytywna") - ostatnia("negatywna")} bez oceny
                  </button>
                </div>
              </div>
            </section>
            {/* Karol 02:04, zgłoszenie 110: prawa kolumna pokazuje kompetencje zespołu w skrócie; średnie i osoby są pod spodem. */}
            {mapa && <MapaKompetencji mapa={mapa} ludzie={ludzie} onWybierz={onWybierz} czesc="wnioski" />}
          </aside>
        )}

        {!zespol && sprawy && (
          <aside className="pulpit-boczna">
            <section className="sekcja">
              <div className="wiersz-tytulu">
                <h2>Twoje cele</h2>
                {onCele && (
                  <button type="button" className="link" onClick={onCele}>
                    Wszystkie
                  </button>
                )}
              </div>
              {cele === null ? (
                <p className="meta">Wczytuję cele…</p>
              ) : cele.length === 0 ? (
                <p className="meta">Nie masz jeszcze celów rozwojowych.</p>
              ) : (
                <ul className="pulpit-cele">
                  {cele.slice(0, 3).map((c) => (
                    <li key={c.id}>
                      <span>{c.nazwa}</span>
                      <span className={`status ${STATUS_CELU[c.status][1]}`}>{STATUS_CELU[c.status][0]}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="sekcja">
              <h2>Ostatnia ocena</h2>
              {ludzie[0]?.ostatnia_ocena_okresowa ? (
                <p className="pulpit-ostatnia">
                  <span className={`status ${ludzie[0].ostatnia_ocena_okresowa.wynik}`}>{ludzie[0].ostatnia_ocena_okresowa.wynik}</span>
                  <span>{data(ludzie[0].ostatnia_ocena_okresowa.data)}</span>
                </p>
              ) : (
                <p className="meta">W aktach nie ma jeszcze oceny okresowej.</p>
              )}
            </section>
          </aside>
        )}
      </div>

      {mapa && sprawy && <MapaKompetencji mapa={mapa} ludzie={ludzie} onWybierz={onWybierz} czesc={zespol ? "tabela" : undefined} />}

      <div className="pulpit-pasek">
        <form className="pole-zapytania" role="search" onSubmit={wyslij}>
          <Ikona nazwa="szukaj" />
          <input
            value={szukaj}
            onChange={(e) => setSzukaj(e.target.value)}
            placeholder={zespol ? "Znajdź pracownika albo zapytaj o zasady oceny…" : "Zapytaj o zasady oceny…"}
            aria-label={zespol ? "Znajdź pracownika albo zapytaj o zasady oceny" : "Zapytaj o zasady oceny"}
            autoComplete="off"
          />
          <button type="submit" className="wyslij" aria-label="Wyślij" disabled={!szukaj.trim()}>
            <Ikona nazwa="gora" />
          </button>
        </form>
      </div>
    </div>
  );
}
