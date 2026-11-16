"""Sign-in by e-mail code and device approval (legacy auth mode, codes captured instead of mailed)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.account_link import routes

ADMIN = "admin@example.com"


@pytest.fixture
def outbox(monkeypatch):
    sent = {}
    monkeypatch.setattr(routes, "send_code", lambda email, code: sent.__setitem__(email, code))
    return sent


def test_email_code_signs_in_once(outbox):
    anonymous = TestClient(app)
    assert anonymous.post("/api/auth/email/start", json={"email": ADMIN}).status_code == 202
    code = outbox[ADMIN]
    session = anonymous.post("/api/auth/email/verify", json={"email": ADMIN, "code": code}).json()
    assert session["token_type"] == "bearer"
    me = TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {session['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == ADMIN
    # A code is single-use.
    assert anonymous.post("/api/auth/email/verify", json={"email": ADMIN, "code": code}).status_code == 400


def test_wrong_codes_lock_the_code(outbox):
    anonymous = TestClient(app)
    anonymous.post("/api/auth/email/start", json={"email": ADMIN})
    wrong = "000000" if outbox[ADMIN] != "000000" else "111111"
    for _ in range(routes.MAX_CODE_ATTEMPTS):
        assert anonymous.post("/api/auth/email/verify", json={"email": ADMIN, "code": wrong}).status_code == 400
    locked = anonymous.post("/api/auth/email/verify", json={"email": ADMIN, "code": outbox[ADMIN]})
    assert locked.status_code == 429


def test_unknown_address_gets_no_session(outbox):
    anonymous = TestClient(app)
    assert anonymous.post("/api/auth/email/start", json={"email": "nobody@example.com"}).status_code == 202
    verify = anonymous.post("/api/auth/email/verify", json={"email": "nobody@example.com", "code": outbox["nobody@example.com"]})
    assert verify.status_code == 403


def test_device_is_connected_by_an_approved_session(client):
    device = TestClient(app)
    start = device.post("/api/auth/device/start", json={"client_name": "ORVECT pour Mac"}).json()
    assert start["verification_uri_complete"].endswith(f"?code={start['user_code']}")
    assert device.post("/api/auth/device/token", json={"device_code": start["device_code"]}).json()["status"] == "pending"

    # The signed-in user (phone or browser) sees the device, typed without the dash, and approves it.
    assert client.get(f"/api/auth/device/{start['user_code'].replace('-', '').lower()}").json()["client_name"] == "ORVECT pour Mac"
    assert client.post(f"/api/auth/device/{start['user_code']}/approve", json={"approve": True}).json()["status"] == "approved"

    granted = device.post("/api/auth/device/token", json={"device_code": start["device_code"]}).json()
    assert granted["status"] == "approved" and granted["email"] == ADMIN
    me = TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {granted['access_token']}"})
    assert me.status_code == 200
    # Handed out once only.
    assert device.post("/api/auth/device/token", json={"device_code": start["device_code"]}).json()["status"] == "consumed"


def test_denied_device_gets_nothing(client):
    device = TestClient(app)
    start = device.post("/api/auth/device/start", json={}).json()
    assert client.post(f"/api/auth/device/{start['user_code']}/approve", json={"approve": False}).json()["status"] == "denied"
    assert device.post("/api/auth/device/token", json={"device_code": start["device_code"]}).json()["status"] == "denied"
    assert client.post(f"/api/auth/device/{start['user_code']}/approve", json={"approve": True}).status_code == 409


def test_approving_requires_a_signed_in_user():
    device = TestClient(app)
    start = device.post("/api/auth/device/start", json={}).json()
    assert TestClient(app).post(f"/api/auth/device/{start['user_code']}/approve", json={"approve": True}).status_code == 401


def test_smtp_provider_sends_a_text_and_html_message(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append((host, port))
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def starttls(self): sent.append("tls")
        def login(self, user, password): sent.append(("login", user))
        def send_message(self, message): sent.append(message)

    monkeypatch.setattr(routes.settings, "email_provider", "smtp")
    monkeypatch.setattr(routes.settings, "smtp_username", "connexion@orvect.fr")
    monkeypatch.setattr(routes.smtplib, "SMTP", FakeSMTP)
    routes.send_code("garage@example.com", "123456")
    message = sent[-1]
    assert sent[:3] == [("smtp.ionos.fr", 587), "tls", ("login", "connexion@orvect.fr")]
    assert message["To"] == "garage@example.com" and "123456" in message["Subject"]
    assert {part.get_content_type() for part in message.iter_parts()} == {"text/plain", "text/html"}
