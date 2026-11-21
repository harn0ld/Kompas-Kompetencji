/** Jeden zestaw ikon interfejsu: kreska 1,75, siatka 24, kolor z currentColor. */
const SCIEZKI = {
  dom: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  osoby:
    "M9 4.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7zM2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5M15.5 4.6a3.5 3.5 0 0 1 0 6.8M17.5 14.8c2 .8 3.4 2.6 4 5.2",
  ksiazka: "M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5zM5 19.5A1.5 1.5 0 0 0 6.5 21H19M9 7h6",
  kalendarz: "M5 5h14v15H5zM5 9.5h14M9 3v4M15 3v4",
  dymek: "M4 5h16v11H10l-6 4zM8 9.5h8M8 12.5h5",
  dalej: "m9 6 6 6-6 6",
  krzyz: "M6 6l12 12M18 6 6 18",
  szukaj: "M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14zm9 16-4-4",
  pytanie: "M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18zM9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.8M12 17.2v.3",
  gora: "M12 19V5M6 11l6-6 6 6",
} as const;

export type NazwaIkony = keyof typeof SCIEZKI;

export function Ikona({ nazwa, rozmiar = 20 }: { nazwa: NazwaIkony; rozmiar?: number }) {
  return (
    <svg className="ikona" width={rozmiar} height={rozmiar} viewBox="0 0 24 24" aria-hidden="true">
      <path d={SCIEZKI[nazwa]} />
    </svg>
  );
}
