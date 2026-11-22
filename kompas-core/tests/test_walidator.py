import pytest

from kompas_core.zrodla import (
    ElementAdnotowany,
    KodBledu,
    Korpus,
    SourceRef,
    cytat_w_korpusie,
    cytat_w_tekscie,
    normalizuj,
    waliduj_elementy,
)


@pytest.fixture
def korpus(manifest) -> Korpus:
    return Korpus.z_manifestu(manifest)


def przepis(cytat: str, doc_id: str = "ustawa", **kw) -> SourceRef:
    return SourceRef(kategoria="PRZEPIS", doc_id=doc_id, cytat_dosłowny=cytat, **kw)


def test_normalizacja_tylko_bialych_znakow_i_dzielenia():
    assert normalizuj("zatrudnio-\nnego  na\tczas") == "zatrudnionego na czas"
    assert normalizuj("Ocena") != normalizuj("ocena")


def test_cytat_z_listy_bez_punktora_przechodzi():
    # poradnik-okresowa s. 25 z PDF: model cytował bez punktora i walidacja odrzucała odpowiedź (22.11)
    tekst = "rozmowę. W jej trakcie omawia: \n główne obowiązki \n postawa • cele"
    assert cytat_w_tekscie("W jej trakcie omawia: główne obowiązki postawa cele", tekst)
    assert cytat_w_tekscie("omawia:  główne obowiązki", tekst)
    assert not cytat_w_tekscie("W jej trakcie omawia: poboczne obowiązki", tekst)


def test_cytat_obecny_przechodzi(korpus):
    assert cytat_w_korpusie("Ocena jest negatywna, gdy jedno kryterium ma 1 punkt.", korpus)


def test_cytat_ze_zmieniona_litera_nie_przechodzi(korpus):
    assert not cytat_w_korpusie("Ocena jest negatywna, gdy jedno kryterium ma 2 punkt.", korpus)
    assert not cytat_w_korpusie("Ocena jest negatywnA", korpus)


def test_lamanie_wyrazu_na_koncu_wiersza_przechodzi(korpus):
    assert cytat_w_korpusie(
        "Pracownik sluzby cywilnej zatrudnionego na czas nieokreslony", korpus, "ustawa"
    )


def test_cytat_przez_granice_stron_i_fragmentow(korpus):
    assert cytat_w_korpusie("w terminie 7 dni.\n§ 11. 1. Ocena jest", korpus, "ustawa", "2024")


def test_cytat_z_docx_i_xlsx(korpus):
    assert cytat_w_korpusie("Data oceny: 14.06.2024", korpus, "arkusz")
    assert not cytat_w_korpusie("14.046.2024", korpus, "arkusz")  # usunięcie nie jest tekstem
    assert cytat_w_korpusie("Rzetelność i terminowość", korpus, "excel")


def test_cytat_w_innym_dokumencie_nie_przechodzi(korpus):
    assert not cytat_w_korpusie("Komunikacja", korpus, "ustawa")


def test_waliduj_elementy_raportuje_bledy(korpus):
    wynik = waliduj_elementy(
        [
            ElementAdnotowany(id="ok", adnotacje=[przepis("Ocene sporzadza sie co 24 miesiace.")]),
            ElementAdnotowany(id="bez", adnotacje=[]),
            ElementAdnotowany(id="zmyslony", adnotacje=[przepis("Ocene sporzadza sie co 36 miesiecy.")]),
            ElementAdnotowany(id="dok", adnotacje=[przepis("x", doc_id="nie-ma")]),
            ElementAdnotowany(id="wersja", adnotacje=[przepis("Ocene", doc_version="1999")]),
            ElementAdnotowany(
                id="funkcja",
                adnotacje=[SourceRef(kategoria="FUNKCJA_APLIKACJI", uzasadnienie="u", zatwierdził="A")],
            ),
        ],
        korpus,
    )
    assert not wynik.ok
    assert wynik.sprawdzone_elementy == 6
    assert wynik.sprawdzone_cytaty == 4
    assert {(b.element_id, b.kod) for b in wynik.bledy} == {
        ("bez", KodBledu.BRAK_ADNOTACJI),
        ("zmyslony", KodBledu.BRAK_POKRYCIA),
        ("dok", KodBledu.NIEZNANY_DOKUMENT),
        ("wersja", KodBledu.NIEZNANY_DOKUMENT),
    }


def test_rozbieznosc_przechodzi_walidacje_gdy_oba_cytaty_sa_w_korpusie(korpus):
    el = ElementAdnotowany(
        id="srednia",
        adnotacje=[
            przepis("Srednia jest liczona ze wszystkich kryteriow."),
            SourceRef(kategoria="OBJAŚNIENIE_MATERIAŁU", doc_id="excel", cytat_dosłowny="Punkty"),
        ],
        rozbieżność={"opis": "Excel liczy inaczej niż § 11", "zastosowana": 0},
    )
    assert waliduj_elementy([el], korpus).ok


def test_raport_korpusu_zawiera_brak_tekstu(korpus):
    statusy = {w.doc_id: w.status.value for w in korpus.raport}
    assert statusy["skan"] == "BRAK_TEKSTU"
