import pytest
from fastapi import HTTPException
from app import firebase_auth
from app.core.config import settings
from app.database.models import FirebaseIdentity
from app.database.session import SessionLocal


def claims(monkeypatch, **values):
    monkeypatch.setattr(firebase_auth, "verify_token", lambda token: {
        "uid": "firebase-admin-test", "email": "admin@example.com",
        "email_verified": True, **values})


def test_verified_existing_account_binds_uid(monkeypatch):
    claims(monkeypatch)
    with SessionLocal() as db:
        context = firebase_auth.firebase_context("valid", db)
        assert context.role == "admin"
        assert db.get(FirebaseIdentity, "firebase-admin-test").user_id == context.user_id
        claims(monkeypatch, email="changed@example.com")
        assert firebase_auth.firebase_context("valid", db).user_id == context.user_id


@pytest.mark.parametrize("values", [{"email_verified": False}, {"email": "stranger@example.com"}])
def test_unverified_or_unassigned_users_denied(monkeypatch, values):
    monkeypatch.setattr(settings, "firebase_self_signup_enabled", False)
    claims(monkeypatch, **values)
    with SessionLocal() as db, pytest.raises(HTTPException) as error:
        firebase_auth.firebase_context("valid", db)
    assert error.value.status_code == 403


def test_recreated_account_cannot_claim_existing_binding(monkeypatch):
    claims(monkeypatch)
    with SessionLocal() as db:
        firebase_auth.firebase_context("valid", db)
        claims(monkeypatch, uid="replacement-uid")
        with pytest.raises(HTTPException) as error:
            firebase_auth.firebase_context("valid", db)
        assert error.value.status_code == 403


def test_verified_signup_gets_isolated_demo_workspace(monkeypatch):
    monkeypatch.setattr(settings, "firebase_self_signup_enabled", True)
    claims(monkeypatch, uid="new-firebase-user", email="new@example.com", name="New User")
    with SessionLocal() as db:
        context = firebase_auth.firebase_context("valid", db)
        assert context.role == "admin"
        vehicles = db.query(firebase_auth.VehicleProfile).filter_by(garage_id=context.garage_id).all()
        assert len(vehicles) == 1 and vehicles[0].is_demo_vehicle


@pytest.mark.parametrize("identity_claim", ["user_id", "sub"])
def test_keyless_firebase_identity_claim_provisions_workspace(monkeypatch, identity_claim):
    monkeypatch.setattr(settings, "firebase_self_signup_enabled", True)
    monkeypatch.setattr(firebase_auth, "verify_token", lambda token: {
        identity_claim: f"keyless-{identity_claim}",
        "email": f"keyless-{identity_claim}@example.com",
        "email_verified": True,
    })
    with SessionLocal() as db:
        context = firebase_auth.firebase_context("valid", db)
        assert context.role == "admin"
        assert db.get(FirebaseIdentity, f"keyless-{identity_claim}").user_id == context.user_id


def test_firebase_mode_rejects_legacy_cookie_and_login(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_provider", "firebase")
    monkeypatch.setattr(settings, "demo_access_without_login", True)
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "admin@example.com", "password": "demo-change-me"}).status_code == 410


def test_invalid_token_never_reaches_database(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_provider", "firebase")
    def reject(token):
        raise HTTPException(401, "Invalid token")
    monkeypatch.setattr(firebase_auth, "verify_token", reject)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_admin_sdk_checks_revocation(monkeypatch):
    from firebase_admin import auth
    marker = object()
    monkeypatch.setattr(firebase_auth, "firebase_app", lambda: marker)
    def verify(token, *, app, check_revoked):
        assert token == "signed-token" and app is marker and check_revoked is True
        return {"uid": "verified"}
    monkeypatch.setattr(auth, "verify_id_token", verify)
    assert firebase_auth.verify_token("signed-token") == {"uid": "verified"}


def test_revoked_firebase_token_rejected(monkeypatch):
    from firebase_admin import auth
    monkeypatch.setattr(firebase_auth, "firebase_app", lambda: object())
    def revoked(*args, **kwargs):
        raise auth.RevokedIdTokenError("Revoked")
    monkeypatch.setattr(auth, "verify_id_token", revoked)
    with pytest.raises(HTTPException) as error:
        firebase_auth.verify_token("revoked")
    assert error.value.status_code == 401


def test_keyless_verification_uses_firebase_public_certificates(monkeypatch):
    from google.oauth2 import id_token
    monkeypatch.setattr(settings, "firebase_check_revoked", False)
    monkeypatch.setattr(settings, "firebase_project_id", "orvect")
    def verify(token, request, *, audience, certs_url):
        assert token == "signed" and audience == "orvect"
        assert certs_url.endswith("securetoken@system.gserviceaccount.com")
        return {"uid": "user", "iss": "https://securetoken.google.com/orvect"}
    monkeypatch.setattr(id_token, "verify_token", verify)
    assert firebase_auth.verify_token("signed")["uid"] == "user"
