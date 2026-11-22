import { useEffect, useRef } from "react";
import type { Sciezka } from "./api";
import AsystentFormalny from "./AsystentFormalny";
import { Ikona } from "./Ikona";
import { Wydra } from "./wydra/Wydra";
import "./okno-asystenta.css";

const PRZYKLADY = [
  "Kiedy przeprowadza się rozmowę wstępną?",
  "Ile kryteriów dodatkowych można wybrać?",
  "Ile dni ma pracownik na sprzeciw od oceny okresowej?",
];

/**
 * Asystent formalny w oknie na środku ekranu (natywny <dialog>: fokus w oknie, Escape, przyciemnione tło).
 * Okno jest stale w drzewie, więc rozmowa zostaje po zamknięciu i ponownym otwarciu.
 */
export function OknoAsystenta({
  otwarte,
  onZamknij,
  sciezka,
  pytanie,
}: {
  otwarte: boolean;
  onZamknij: () => void;
  /** Ścieżka bieżącego procesu: asystent szuka wtedy tylko w jej rozporządzeniu (#37). */
  sciezka?: Sciezka;
  /** Pytanie z pulpitu; zmiana `id` wysyła je do asystenta. */
  pytanie?: { id: number; tekst: string } | null;
}) {
  const okno = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = okno.current;
    if (!d) return;
    if (otwarte && !d.open) d.showModal();
    if (!otwarte && d.open) d.close();
  }, [otwarte]);

  return (
    <dialog
      ref={okno}
      className="okno-asystenta"
      aria-labelledby="okno-asystenta-tytul"
      onClose={onZamknij}
      // Klik w przyciemnione tło trafia w sam <dialog>; treść okna wypełnia go w całości.
      onClick={(e) => e.target === e.currentTarget && onZamknij()}
    >
      <div className="okno">
        <div className="okno-glowa">
          <Wydra poza="stoi" szerokosc={48} naStart="machanie" />
          <div>
            <h2 id="okno-asystenta-tytul">Asystent formalny</h2>
            <p className="meta">Odpowiada na podstawie materiałów MC i instrukcji aplikacji</p>
          </div>
          <button type="button" className="ikona-przycisk" aria-label="Zamknij asystenta" onClick={onZamknij}>
            <Ikona nazwa="krzyz" />
          </button>
        </div>
        <div className="okno-cialo">
          <AsystentFormalny sciezka={sciezka} przyklady={PRZYKLADY} pytanieZZewnatrz={pytanie} />
        </div>
      </div>
    </dialog>
  );
}
