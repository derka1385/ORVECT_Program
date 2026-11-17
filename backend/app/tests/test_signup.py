"""Garage sign-up: SIRET checked against the company register (mocked here), then an e-mail code."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.account_link import routes, signup

GARAGE = "44163946500091"  # a real, Luhn-valid SIRET; the register answer below is made up
EMAIL = "nolann@garage-test.fr"


@pytest.fixture
def outbox(monkeypatch):
    sent = {}
    monkeypatch.setattr(routes, "send_code", lambda email, code: sent.__setitem__(email, code))
    return sent


@pytest.fixture
def register(monkeypatch):
    places = {GARAGE: {"name": "Garage du Centre", "legal_name": "GARAGE DU CENTRE SARL",
                       "address": "1 rue de la Gare 69001 Lyon", "naf_code": "45.20A", "active": True}}
    monkeypatch.setattr(signup, "lookup_siret", lambda siret: places.get(siret))
    return places


def test_siret_key_is_checked():
    assert signup.valid_siret(GARAGE)
    assert not signup.valid_siret("44163946500092")
    assert not signup.valid_siret("1234")
    assert signup.valid_siret("35600000000010")  # La Poste: digit sum divisible by 5


def test_garage_signs_up_with_its_siret(outbox, register):
    anonymous = TestClient(app)
    preview = anonymous.get(f"/api/auth/signup/siret/{GARAGE[:3]} {GARAGE[3:]}").json()
    assert preview["eligible"] and preview["naf_label"].startswith("Entretien et réparation")

    start = anonymous.post("/api/auth/signup/start", json={"email": EMAIL, "siret": GARAGE, "first_name": "Nolann"})
    assert start.status_code == 202 and start.json()["garage_name"] == "Garage du Centre"
    session = anonymous.post("/api/auth/signup/verify", json={"email": EMAIL, "code": outbox[EMAIL]}).json()
    assert session["token_type"] == "bearer" and session["garage_name"] == "Garage du Centre"
    me = TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {session['access_token']}"}).json()
    assert me["email"] == EMAIL and me["role"] == "admin"

    # The SIRET is now taken: a second person must be invited by the admin.
    again = anonymous.get(f"/api/auth/signup/siret/{GARAGE}").json()
    assert not again["eligible"] and "administrateur" in again["reason"]
    other = anonymous.post("/api/auth/signup/start", json={"email": "autre@garage-test.fr", "siret": GARAGE})
    assert other.status_code == 422


def test_closed_or_non_automotive_establishments_are_refused(outbox, register):
    register[GARAGE] = {**register[GARAGE], "naf_code": "64.20Z"}
    assert "NAF 45" in TestClient(app).get(f"/api/auth/signup/siret/{GARAGE}").json()["reason"]
    register[GARAGE] = {**register[GARAGE], "naf_code": "45.20A", "active": False}
    refused = TestClient(app).post("/api/auth/signup/start", json={"email": EMAIL, "siret": GARAGE})
    assert refused.status_code == 422 and "fermé" in refused.json()["detail"]
    assert outbox == {}


def test_unknown_or_invalid_siret(register):
    assert "pas valide" in TestClient(app).get("/api/auth/signup/siret/12345678901234").json()["reason"]
    assert not TestClient(app).get("/api/auth/signup/siret/73282932000074").json()["found"]


def test_existing_address_signs_in_instead(outbox, register):
    taken = TestClient(app).post("/api/auth/signup/start", json={"email": "admin@example.com", "siret": GARAGE})
    assert taken.status_code == 409


def test_wrong_codes_lock_the_sign_up(outbox, register):
    anonymous = TestClient(app)
    anonymous.post("/api/auth/signup/start", json={"email": EMAIL, "siret": GARAGE})
    wrong = "000000" if outbox[EMAIL] != "000000" else "111111"
    for _ in range(routes.MAX_CODE_ATTEMPTS):
        assert anonymous.post("/api/auth/signup/verify", json={"email": EMAIL, "code": wrong}).status_code == 400
    assert anonymous.post("/api/auth/signup/verify", json={"email": EMAIL, "code": outbox[EMAIL]}).status_code == 429
