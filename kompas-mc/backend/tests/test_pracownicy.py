import pytest


def ids(klient, naglowek, login):
    return [p["osoba_id"] for p in klient.get("/api/pracownicy", headers=naglowek(login)).json()]


def test_bez_logowania_401(klient):
    assert klient.get("/api/pracownicy").status_code == 401
    assert klient.post("/api/auth/login", json={"login": "hr", "hasło": "zle"}).status_code == 401


def test_przelozony_widzi_tylko_swoich_podwladnych(klient, naglowek):
    assert sorted(ids(klient, naglowek, "przelozony1")) == [
        "P-101", "P-104", "P-105", "P-111", "P-114", "P-115", "P-121", "P-124", "P-125",
        "P-202", "P-203", "P-212", "P-213", "P-222", "P-223",
    ]
    assert sorted(ids(klient, naglowek, "przelozony2")) == [
        "P-102", "P-103", "P-112", "P-113", "P-122", "P-123", "P-201", "P-204", "P-211", "P-214", "P-221", "P-224",
    ]
    h = naglowek("przelozony1")
    assert klient.get("/api/pracownicy/P-101", headers=h).status_code == 200
    assert klient.get("/api/pracownicy/P-102", headers=h).status_code == 403


def test_oceniany_widzi_tylko_siebie_a_hr_wszystkich(klient, naglowek):
    assert ids(klient, naglowek, "oceniany") == ["P-101"]
    assert klient.get("/api/pracownicy/P-104", headers=naglowek("oceniany")).status_code == 403
    assert len(ids(klient, naglowek, "hr")) == 29


def test_nieznana_osoba_404_a_ja_zwraca_role(klient, naglowek):
    h = naglowek("hr")
    assert klient.get("/api/pracownicy/P-999", headers=h).status_code == 404
    assert klient.get("/api/ja", headers=h).json() == {
        "login": "hr",
        "rola": "hr",
        "osoba_id": None,
    }


@pytest.mark.parametrize("pole", ["scenariusz", "oczekiwany_arkusz"])
def test_odpowiedz_bez_danych_testowych(klient, naglowek, pole):
    p = klient.get("/api/pracownicy/P-101", headers=naglowek("przelozony1")).json()
    assert p["nazwisko"] == "Zielińska-Demo" and pole not in p


def test_kontrakt_mocka_qnt_w_openapi(klient):
    spec = klient.get("/openapi.json").json()
    assert {"/api/auth/login", "/api/ja", "/api/pracownicy", "/api/pracownicy/{osoba_id}"} <= set(
        spec["paths"]
    )
    assert "Pracownik" in spec["components"]["schemas"]


def test_poprzednia_ocena_z_punktami_tylko_dla_dostepu_do_tresci(klient, naglowek):
    """Przełożony i oceniany widzą punkty poprzedniej oceny; HR i cudzy przełożony dostają 403."""
    url = "/api/pracownicy/P-101/poprzednia-ocena"
    r = klient.get(url, headers=naglowek("przelozony1")).json()
    assert r["wynik"] == "pozytywna" and r["data"] == "2024-12-02" and r["punkty"]["rzetelnosc"] in {1, 3, 5, 7, 9}
    assert klient.get(url, headers=naglowek("oceniany")).status_code == 200
    assert klient.get(url, headers=naglowek("hr")).status_code == 403
    assert klient.get(url, headers=naglowek("przelozony2")).status_code == 403
    assert "punkty" not in str(klient.get("/api/pracownicy/P-101", headers=naglowek("przelozony1")).json())
