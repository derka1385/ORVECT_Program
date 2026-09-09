"""Firebase identities authenticate; database memberships authorize access."""
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.database.models import (
    FirebaseIdentity, Garage, GarageMembership, User, VehicleConfiguration,
    VehicleProfile,
)


def provision_isolated_workspace(claims, db):
    if not settings.firebase_self_signup_enabled:
        return None
    email = str(claims["email"]).lower()
    display_name = str(claims.get("name") or email.split("@", 1)[0])[:160]
    garage = Garage(name=f"Espace de {display_name}"[:200])
    db.add(garage)
    db.flush()
    user = User(garage_id=garage.id, email=email, display_name=display_name, role="admin", password_hash=None)
    db.add(user)
    db.flush()
    db.add(GarageMembership(user_id=user.id, garage_id=garage.id, role="admin"))
    golf = VehicleProfile(
        garage_id=garage.id, make="Volkswagen", model="Golf VII", year=2018,
        market="EU", engine_name="1.4 TSI 92 kW", engine_code="CZCA",
        fuel_type="gasoline", transmission="manual",
        notes="Véhicule VAG de démonstration, entièrement synthétique.", is_demo_vehicle=True,
    )
    db.add(golf)
    db.flush()
    db.add(VehicleConfiguration(
        vehicle_id=golf.id, manufacturer="Volkswagen Group", make="Volkswagen",
        model="Golf VII", generation="VII", model_year=2018, market="EU",
        vehicle_type="passenger_car", body_type="hatchback", fuel_type="gasoline",
        engine_family="EA211", engine_name="1.4 TSI 92 kW", engine_code="CZCA",
        engine_code_confirmed_by_user="CZCA", engine_displacement_cc=1395,
        engine_power_kw=92, transmission_type="manual", drivetrain="FWD", platform="MQB",
        providers_used=["internal_demo"], field_provenance={"scope": "synthetic_demo"},
        precision_level="demo_fixture", confidence_score=1.0, confirmed_by_user=True,
        confirmed_by_user_id=user.id,
    ))
    return user


@lru_cache(maxsize=1)
def firebase_app():
    import firebase_admin
    # Uses GOOGLE_APPLICATION_CREDENTIALS / Application Default Credentials.
    return firebase_admin.initialize_app(options={"projectId": settings.firebase_project_id}, name="orvect-auth")


def verify_token(token):
    from firebase_admin import auth
    try:
        app = firebase_app()
    except Exception as exc:
        raise HTTPException(503, "Firebase authentication is not configured") from exc
    try:
        return auth.verify_id_token(token, app=app, check_revoked=True)
    except (auth.InvalidIdTokenError, auth.UserDisabledError, ValueError) as exc:
        raise HTTPException(401, "Invalid or expired Firebase session") from exc
    except Exception as exc:
        raise HTTPException(503, "Firebase authentication temporarily unavailable") from exc


def firebase_context(token, db):
    from app.auth import AuthContext
    if not token:
        raise HTTPException(401, "Authentication required")
    claims = verify_token(token)
    if claims.get("email_verified") is not True:
        raise HTTPException(403, "Vérifiez votre adresse e-mail avant de continuer.")
    uid = claims.get("uid")
    email = str(claims.get("email", "")).lower()
    if not uid or not email:
        raise HTTPException(401, "Firebase identity is incomplete")
    identity = db.get(FirebaseIdentity, uid)
    user = db.get(User, identity.user_id) if identity else db.scalar(select(User).where(User.email == email))
    if not user:
        user = provision_isolated_workspace(claims, db)
    if not user or not user.is_active:
        raise HTTPException(403, "Compte vérifié, mais aucun accès ORVECT ne lui a été attribué.")
    db.flush()
    memberships = db.scalars(select(GarageMembership).where(
        GarageMembership.user_id == user.id, GarageMembership.is_active.is_(True)
    )).all()
    if len(memberships) != 1 or memberships[0].role not in {"admin", "technician"}:
        raise HTTPException(403, "Un accès actif à un garage est nécessaire.")
    if not identity:
        # One-time migration of an existing account, only after Google verified email ownership.
        db.add(FirebaseIdentity(uid=uid, user_id=user.id))
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(403, "Ce compte est déjà associé à une autre identité Firebase.") from exc
    member = memberships[0]
    return AuthContext(user.id, member.garage_id, member.role, user.email)
