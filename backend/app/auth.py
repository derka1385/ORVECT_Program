import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import AuthSession, GarageMembership, User, now
from app.database.session import get_db


PBKDF2_ITERATIONS = 310_000
bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/auth", tags=["authentication"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(StrictModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    garage_id: str
    role: Literal["admin", "technician"]
    email: str


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, PBKDF2_ITERATIONS)
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PBKDF2_ITERATIONS),
            base64.urlsafe_b64encode(actual_salt).decode(),
            base64.urlsafe_b64encode(digest).decode(),
        )
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, raw_iterations, raw_salt, raw_digest = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        if iterations < PBKDF2_ITERATIONS:
            return False
        salt = base64.urlsafe_b64decode(raw_salt.encode())
        expected = base64.urlsafe_b64decode(raw_digest.encode())
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= datetime.now(timezone.utc)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else request.cookies.get("diagpilot_session")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == _token_hash(token),
            AuthSession.revoked_at.is_(None),
        )
    )
    if not session or _is_expired(session.expires_at):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired authentication token")
    user = db.get(User, session.user_id)
    membership = db.scalar(
        select(GarageMembership).where(
            GarageMembership.user_id == session.user_id,
            GarageMembership.garage_id == session.garage_id,
            GarageMembership.is_active.is_(True),
        )
    )
    if not user or not user.is_active or not membership or membership.role not in {"admin", "technician"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Garage membership is not active")
    return AuthContext(user.id, membership.garage_id, membership.role, user.email)


def active_garage_id(auth: AuthContext = Depends(get_current_user)) -> str:
    return auth.garage_id


def authenticated_user_id(auth: AuthContext = Depends(get_current_user)) -> str:
    return auth.user_id


def require_admin(auth: AuthContext = Depends(get_current_user)) -> AuthContext:
    if auth.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    return auth


@router.post("/login")
def login(data: LoginInput, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    memberships = db.scalars(
        select(GarageMembership).where(
            GarageMembership.user_id == user.id,
            GarageMembership.is_active.is_(True),
        )
    ).all()
    if len(memberships) != 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A user must have exactly one active garage in the minimal authentication implementation",
        )
    membership = memberships[0]
    token = secrets.token_urlsafe(32)
    expires_at = now() + timedelta(hours=settings.auth_session_ttl_hours)
    db.add(
        AuthSession(
            token_hash=_token_hash(token),
            user_id=user.id,
            garage_id=membership.garage_id,
            expires_at=expires_at,
        )
    )
    db.commit()
    response.set_cookie(
        "diagpilot_session",
        token,
        httponly=True,
        secure=settings.app_environment == "production",
        samesite="strict",
        max_age=settings.auth_session_ttl_hours * 3600,
        path="/",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": membership.role,
            "garage_id": membership.garage_id,
        },
    }


@router.get("/me")
def me(auth: AuthContext = Depends(get_current_user)):
    return {
        "id": auth.user_id,
        "email": auth.email,
        "role": auth.role,
        "garage_id": auth.garage_id,
    }


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = credentials.credentials if credentials else request.cookies.get("diagpilot_session", "")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if session and session.user_id == auth.user_id:
        session.revoked_at = now()
        db.commit()
    response.delete_cookie("diagpilot_session", path="/")
    return None
