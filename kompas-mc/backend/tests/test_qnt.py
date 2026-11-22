from datetime import date

from kompas_mc.qnt import MockQnt
from kompas_mc.ustawienia import KATALOG_MC

QNT = KATALOG_MC / "konfiguracja" / "qnt.yaml"


def test_dane_qnt_wczytuja_sie_i_sa_spojne():
    qnt = MockQnt.z_pliku(QNT)
    ids = [p.osoba_id for p in qnt.pracownicy]
    assert len(ids) == len(set(ids)) == 29  # 11 + 18 rekordów testowych (po dwie kopie każdego przypadku)
    assert qnt.dzis_demo == date(2026, 11, 21)
    przelozeni = {p.przelozony_id for p in qnt.pracownicy} - {"P-000"}  # P-000: poza demo
    assert przelozeni == {"P-001", "P-002"} and all(qnt.pracownik(i) for i in przelozeni)


def test_dane_testowe_nie_trafiaja_do_odpowiedzi():
    p = MockQnt.z_pliku(QNT).pracownik("P-101")
    dane = p.model_dump()
    assert p.oczekiwany_arkusz == "C"
    assert "oczekiwany_arkusz" not in dane and "scenariusz" not in dane
