"""Garage sign-up: a SIRET checked against the public company register, then an e-mail code.

1. ``GET /api/auth/signup/siret/{siret}``: what the register says about the establishment (name, address,
   activity, open or closed) and whether it can sign up.
2. ``POST /api/auth/signup/start``: checks the SIRET again on the server, then e-mails a 6-digit code.
3. ``POST /api/auth/signup/verify``: creates the garage, its first admin and the session.

The register is the State's free company search (recherche-entreprises.api.gouv.fr), no key needed.
A SIRET already used by a garage cannot sign up again: its admin invites the others.
"""
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Garage, SignupRequest, User, now
from app.database.session import get_db
from app.firebase_auth import create_workspace
from app.modules.account_link import routes as accounts

router = APIRouter(prefix="/api/auth/signup", tags=["account-linking"])
log = logging.getLogger("orvect.signup")

NAF_LABELS = {
    "45.11Z": "Commerce de voitures et de véhicules automobiles légers",
    "45.19Z": "Commerce d’autres véhicules automobiles",
    "45.20A": "Entretien et réparation de véhicules automobiles légers",
    "45.20B": "Entretien et réparation d’autres véhicules automobiles",
    "45.31Z": "Commerce de gros d’équipements automobiles",
    "45.32Z": "Commerce de détail d’équipements automobiles",
    "45.40Z": "Commerce et réparation de motocycles",
}


def valid_siret(siret: str) -> bool:
    """14 digits with a valid Luhn key (La Poste establishments use their own rule)."""
    if not re.fullmatch(r"\d{14}", siret):
        return False
    if siret.startswith("356000000"):
        return sum(map(int, siret)) % 5 == 0
    total = 0
    for position, char in enumerate(reversed(siret)):
        digit = int(char) * (2 if position % 2 else 1)
        total += digit - 9 if digit > 9 else digit
    return total % 10 == 0


def lookup_siret(siret: str) -> dict | None:
    """The establishment as the public register describes it, or None if it does not exist."""
    try:
        response = httpx.get(settings.company_register_url, params={"q": siret, "per_page": 1}, timeout=8)
        response.raise_for_status()
        results = response.json().get("results") or []
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Company register unavailable: %s", exc)
        raise HTTPException(503, "Le registre des entreprises ne répond pas. Réessayez dans un instant.") from exc
    for company in results:
        for place in company.get("matching_etablissements") or []:
            if place.get("siret") != siret:
                continue
            signs = place.get("liste_enseignes") or []
            name = (signs[0] if signs else None) or place.get("nom_commercial") \
                or company.get("nom_raison_sociale") or company.get("nom_complet") or "Garage"
            return {
                "name": name.strip()[:200],
                "legal_name": company.get("nom_complet"),
                "address": place.get("adresse"),
                "naf_code": place.get("activite_principale") or company.get("activite_principale"),
                "active": place.get("etat_administratif") == "A",
            }
    return None


def check(siret: str, db: Session) -> dict:
    """Everything the apps show about a SIRET, and whether it may sign up (`eligible`, else `reason`)."""
    siret = re.sub(r"\s", "", siret)
    if not valid_siret(siret):
        return {"siret": siret, "found": False, "eligible": False,
                "reason": "Ce numéro SIRET n’est pas valide : il compte 14 chiffres, vérifiez-le."}
    place = lookup_siret(siret)
    if not place:
        return {"siret": siret, "found": False, "eligible": False,
                "reason": "Aucun établissement ne porte ce numéro SIRET dans le registre des entreprises."}
    naf = place["naf_code"] or ""
    answer = {"siret": siret, "found": True, **place, "naf_label": NAF_LABELS.get(naf), "eligible": False}
    prefixes = [p.strip() for p in settings.signup_naf_prefixes.split(",") if p.strip()]
    if not place["active"]:
        answer["reason"] = "Cet établissement est fermé d’après le registre des entreprises."
    elif prefixes and not any(naf.startswith(p) for p in prefixes):
        answer["reason"] = ("ORVECT est réservé aux professionnels de l’automobile (code NAF 45). "
                            "Si vous réparez des véhicules, écrivez-nous à contact@orvect.fr.")
    elif db.scalar(select(Garage.id).where(Garage.siret == siret)):
        answer["reason"] = "Ce garage a déjà un compte ORVECT. Demandez à son administrateur de vous inviter."
    else:
        answer["eligible"] = True
    return answer


@router.get("/siret/{siret}")
def siret_check(siret: str, db: Session = Depends(get_db)):
    return check(siret, db)


class SignupStart(BaseModel):
    email: EmailStr
    siret: str = Field(min_length=14, max_length=20)
    first_name: str = Field(default="", max_length=80)


class SignupVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


@router.post("/start", status_code=202)
def signup_start(data: SignupStart, db: Session = Depends(get_db)):
    email = data.email.lower()
    if settings.email_provider == "console" and settings.app_environment == "production":
        raise HTTPException(503, "L’envoi des codes par e-mail n’est pas configuré sur ce serveur.")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Un compte ORVECT existe déjà avec cette adresse. Connectez-vous.")
    place = check(data.siret, db)
    if not place["eligible"]:
        raise HTTPException(422, place["reason"])
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = [row for row in db.scalars(select(SignupRequest).where(SignupRequest.email == email)).all()
              if (row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)) > hour_ago]
    if len(recent) >= settings.login_codes_per_hour:
        raise HTTPException(429, "Trop de codes demandés pour cette adresse. Réessayez dans une heure.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(SignupRequest(
        email=email, display_name=(data.first_name.strip() or email.split("@", 1)[0])[:160],
        siret=place["siret"], garage_name=place["name"], naf_code=place["naf_code"],
        code_hash=accounts._hash(f"{email}:{code}"),
        expires_at=now() + timedelta(minutes=settings.login_code_ttl_minutes),
    ))
    db.flush()
    try:
        accounts.send_code(email, code)
    except Exception as exc:
        db.rollback()
        log.exception("Sign-up code e-mail failed")
        raise HTTPException(503, "L’e-mail n’a pas pu être envoyé. Réessayez dans un instant.") from exc
    db.commit()
    return {"sent": True, "expires_in": settings.login_code_ttl_minutes * 60, "garage_name": place["name"]}


@router.post("/verify")
def signup_verify(data: SignupVerify, db: Session = Depends(get_db)):
    email = data.email.lower()
    candidates = db.scalars(
        select(SignupRequest).where(SignupRequest.email == email, SignupRequest.consumed_at.is_(None))
        .order_by(SignupRequest.created_at.desc())
    ).all()
    row = next((item for item in candidates if not accounts._expired(item.expires_at)), None)
    if not row:
        raise HTTPException(400, "Ce code a expiré. Demandez-en un nouveau.")
    if row.attempts >= accounts.MAX_CODE_ATTEMPTS:
        raise HTTPException(429, "Trop d’essais. Demandez un nouveau code.")
    if not hmac.compare_digest(row.code_hash, accounts._hash(f"{email}:{data.code}")):
        row.attempts += 1
        db.commit()
        raise HTTPException(400, "Code incorrect.")
    row.consumed_at = now()
    # Another sign-up may have taken the address or the SIRET while this code was on its way.
    if db.scalar(select(User.id).where(User.email == email)):
        db.commit()
        raise HTTPException(409, "Un compte ORVECT existe déjà avec cette adresse. Connectez-vous.")
    if db.scalar(select(Garage.id).where(Garage.siret == row.siret)):
        db.commit()
        raise HTTPException(409, "Ce garage a déjà un compte ORVECT. Demandez à son administrateur de vous inviter.")
    garage = Garage(name=row.garage_name, siret=row.siret, naf_code=row.naf_code, siret_verified_at=now())
    create_workspace(db, garage, email, row.display_name)
    db.commit()
    return {**accounts._session_for_email(db, email, create=True), "garage_name": garage.name}
