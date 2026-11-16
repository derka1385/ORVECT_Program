"""Sign-in without a password, shared by every ORVECT surface.

Two ways in, both ending with a session for the device that asked:
- e-mail code: the server mails a 6-digit code; typing it proves ownership of the address;
- device approval (QR code): a device such as ORVECT for Mac shows a short code, a signed-in
  user approves it on the ORVECT site from a phone or any browser, and the device receives its
  own session (the OAuth 2.0 device authorization flow, RFC 8628, in a reduced form).

In Firebase mode the session is a Firebase custom token, which the client exchanges for its own
Firebase session; in legacy mode it is an API bearer token. Codes are stored hashed only.
"""
import hashlib
import hmac
import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthContext, get_current_user, open_session
from app.core.config import settings
from app.database.models import DeviceAuthorization, FirebaseIdentity, GarageMembership, LoginCode, User, now
from app.database.session import get_db

router = APIRouter(prefix="/api/auth", tags=["account-linking"])
log = logging.getLogger("orvect.account_link")

# Unambiguous characters only: no 0/O, no 1/I.
USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_CODE_ATTEMPTS = 5
POLL_INTERVAL_SECONDS = 3


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= datetime.now(timezone.utc)


# --- Sessions -----------------------------------------------------------------

def _firebase_custom_token(uid: str) -> str:
    from firebase_admin import auth

    from app.firebase_auth import firebase_app

    try:
        token = auth.create_custom_token(uid, app=firebase_app())
    except Exception as exc:  # missing service account credentials, IAM refusal…
        log.exception("Firebase custom token refused")
        raise HTTPException(503, "La connexion sans mot de passe n’est pas encore configurée sur ce serveur.") from exc
    return token.decode() if isinstance(token, bytes) else token


def _session_for_email(db: Session, email: str) -> dict:
    """Session for whoever proved ownership of `email` with a code."""
    if settings.auth_provider == "firebase":
        from firebase_admin import auth

        from app.firebase_auth import firebase_app

        try:
            user = auth.get_user_by_email(email, app=firebase_app())
        except auth.UserNotFoundError:
            if not settings.firebase_self_signup_enabled:
                raise HTTPException(403, "Aucun compte ORVECT n’est associé à cette adresse.")
            user = auth.create_user(email=email, email_verified=True, app=firebase_app())
        except Exception as exc:
            raise HTTPException(503, "Le service de comptes est momentanément indisponible.") from exc
        if not user.email_verified:
            # The code just proved that this person receives mail at this address.
            auth.update_user(user.uid, email_verified=True, app=firebase_app())
        return {"token_type": "firebase_custom", "custom_token": _firebase_custom_token(user.uid), "email": email}

    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    membership = user and db.scalar(
        select(GarageMembership).where(GarageMembership.user_id == user.id, GarageMembership.is_active.is_(True))
    )
    if not user or not membership:
        raise HTTPException(403, "Aucun compte ORVECT n’est associé à cette adresse.")
    token, expires_at = open_session(db, user.id, membership.garage_id)
    return {"token_type": "bearer", "access_token": token, "expires_at": expires_at.isoformat(), "email": email}


def _session_for_device(db: Session, row: DeviceAuthorization) -> dict:
    user = db.get(User, row.user_id) if row.user_id else None
    email = user.email if user else None
    if settings.auth_provider == "firebase":
        if not row.firebase_uid:
            raise HTTPException(409, "Le compte qui a validé ce Mac n’est pas lié à Firebase.")
        return {"token_type": "firebase_custom", "custom_token": _firebase_custom_token(row.firebase_uid), "email": email}
    token, expires_at = open_session(db, row.user_id, row.garage_id)
    return {"token_type": "bearer", "access_token": token, "expires_at": expires_at.isoformat(), "email": email}


# --- E-mail code ----------------------------------------------------------------

def send_code(email: str, code: str) -> None:
    minutes = settings.login_code_ttl_minutes
    subject = f"{code} est votre code de connexion ORVECT"
    text = (f"Votre code de connexion ORVECT : {code}\n\n"
            f"Il expire dans {minutes} minutes et ne sert qu’une fois.\n"
            "Si vous n’avez rien demandé, ignorez cet e-mail : personne ne peut se connecter sans ce code.")
    html = f"""<div style="background:#f2f1ed;padding:32px 0;font-family:'Space Grotesk',Helvetica,Arial,sans-serif;color:#101214">
<div style="max-width:480px;margin:0 auto;background:#ffffff;border:1px solid #d4d2c9;border-radius:4px;overflow:hidden">
<div style="background:#101214;color:#f2f1ed;padding:18px 24px;font-weight:700;font-size:18px;letter-spacing:-0.5px"><span style="color:#ff5c28">///</span> ORVECT</div>
<div style="padding:28px 24px">
<p style="margin:0 0 16px;font-size:15px">Votre code de connexion :</p>
<p style="margin:0 0 20px;font-size:34px;font-weight:700;letter-spacing:8px">{code}</p>
<p style="margin:0;font-size:13px;color:#4b5056">Il expire dans {minutes} minutes et ne sert qu’une fois. Si vous n’avez rien demandé, ignorez cet e-mail : personne ne peut se connecter sans ce code.</p>
</div></div></div>"""
    if settings.email_provider == "smtp":
        message = EmailMessage()
        message["From"] = settings.email_from
        message["To"] = email
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return
    if settings.email_provider == "resend":
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [email], "subject": subject, "text": text, "html": html},
            timeout=10,
        )
        response.raise_for_status()
        return
    # Development only: the code is written to the server log instead of being sent.
    log.warning("Code de connexion ORVECT pour %s : %s", email, code)


class EmailStart(BaseModel):
    email: EmailStr


class EmailVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


@router.post("/email/start", status_code=202)
def email_start(data: EmailStart, db: Session = Depends(get_db)):
    email = data.email.lower()
    if settings.email_provider == "console" and settings.app_environment == "production":
        raise HTTPException(503, "L’envoi des codes par e-mail n’est pas configuré sur ce serveur.")
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = [row for row in db.scalars(select(LoginCode).where(LoginCode.email == email)).all()
              if (row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)) > hour_ago]
    if len(recent) >= settings.login_codes_per_hour:
        raise HTTPException(429, "Trop de codes demandés pour cette adresse. Réessayez dans une heure.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(LoginCode(email=email, code_hash=_hash(f"{email}:{code}"),
                     expires_at=now() + timedelta(minutes=settings.login_code_ttl_minutes)))
    db.flush()
    try:
        send_code(email, code)
    except Exception as exc:
        db.rollback()
        log.exception("Login code e-mail failed")
        raise HTTPException(503, "L’e-mail n’a pas pu être envoyé. Réessayez dans un instant.") from exc
    db.commit()
    # Same answer whether or not an account exists: the address is only checked once the code is typed.
    return {"sent": True, "expires_in": settings.login_code_ttl_minutes * 60}


@router.post("/email/verify")
def email_verify(data: EmailVerify, db: Session = Depends(get_db)):
    email = data.email.lower()
    candidates = db.scalars(
        select(LoginCode).where(LoginCode.email == email, LoginCode.consumed_at.is_(None)).order_by(LoginCode.created_at.desc())
    ).all()
    row = next((item for item in candidates if not _expired(item.expires_at)), None)
    if not row:
        raise HTTPException(400, "Ce code a expiré. Demandez-en un nouveau.")
    if row.attempts >= MAX_CODE_ATTEMPTS:
        raise HTTPException(429, "Trop d’essais. Demandez un nouveau code.")
    if not hmac.compare_digest(row.code_hash, _hash(f"{email}:{data.code}")):
        row.attempts += 1
        db.commit()
        raise HTTPException(400, "Code incorrect.")
    row.consumed_at = now()
    db.commit()
    return _session_for_email(db, email)


# --- Device approval (QR code) -------------------------------------------------

class DeviceStart(BaseModel):
    client_name: str = Field(default="ORVECT pour Mac", min_length=1, max_length=120)


class DeviceToken(BaseModel):
    device_code: str = Field(min_length=20, max_length=200)


class DeviceDecision(BaseModel):
    approve: bool = True


def _normalize(user_code: str) -> str:
    raw = "".join(ch for ch in user_code.upper() if ch.isalnum())
    return f"{raw[:4]}-{raw[4:8]}" if len(raw) == 8 else user_code.upper()


def _awaiting(db: Session, user_code: str) -> DeviceAuthorization:
    row = db.scalar(select(DeviceAuthorization).where(DeviceAuthorization.user_code == _normalize(user_code)))
    if not row:
        raise HTTPException(404, "Code inconnu. Vérifiez le code affiché sur le Mac.")
    if row.status != "pending" or row.consumed_at:
        raise HTTPException(409, "Ce code a déjà été utilisé.")
    if _expired(row.expires_at):
        raise HTTPException(410, "Ce code a expiré. Générez-en un nouveau sur le Mac.")
    return row


@router.post("/device/start", status_code=201)
def device_start(data: DeviceStart, db: Session = Depends(get_db)):
    device_code = secrets.token_urlsafe(32)
    for _ in range(5):
        user_code = "-".join("".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(4)) for _ in range(2))
        if not db.scalar(select(DeviceAuthorization.id).where(DeviceAuthorization.user_code == user_code)):
            break
    ttl = settings.device_code_ttl_minutes * 60
    db.add(DeviceAuthorization(device_code_hash=_hash(device_code), user_code=user_code, client_name=data.client_name,
                               expires_at=now() + timedelta(seconds=ttl)))
    db.commit()
    return {
        "device_code": device_code,
        "user_code": user_code,
        "verification_uri": settings.device_verification_url,
        "verification_uri_complete": f"{settings.device_verification_url}{'&' if '?' in settings.device_verification_url else '?'}code={user_code}",
        "expires_in": ttl,
        "interval": POLL_INTERVAL_SECONDS,
    }


@router.post("/device/token")
def device_token(data: DeviceToken, db: Session = Depends(get_db)):
    """Polled by the device. The session is handed out once, then the request is spent."""
    row = db.scalar(select(DeviceAuthorization).where(DeviceAuthorization.device_code_hash == _hash(data.device_code)))
    if not row:
        raise HTTPException(404, "Demande de connexion inconnue.")
    if row.consumed_at:
        return {"status": "consumed"}
    if row.status == "denied":
        return {"status": "denied"}
    if row.status != "approved":
        return {"status": "expired" if _expired(row.expires_at) else "pending", "interval": POLL_INTERVAL_SECONDS}
    row.consumed_at = now()
    db.commit()
    return {"status": "approved", **_session_for_device(db, row)}


@router.get("/device/{user_code}")
def device_info(user_code: str, db: Session = Depends(get_db), auth: AuthContext = Depends(get_current_user)):
    row = _awaiting(db, user_code)
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    return {"user_code": row.user_code, "client_name": row.client_name, "email": auth.email,
            "expires_in": max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))}


@router.post("/device/{user_code}/approve")
def device_approve(user_code: str, data: DeviceDecision, db: Session = Depends(get_db),
                   auth: AuthContext = Depends(get_current_user)):
    row = _awaiting(db, user_code)
    if not data.approve:
        row.status = "denied"
        db.commit()
        return {"status": "denied"}
    row.status = "approved"
    row.approved_at = now()
    row.user_id = auth.user_id
    row.garage_id = auth.garage_id
    if settings.auth_provider == "firebase":
        row.firebase_uid = db.scalar(select(FirebaseIdentity.uid).where(FirebaseIdentity.user_id == auth.user_id))
    db.commit()
    return {"status": "approved", "client_name": row.client_name}
