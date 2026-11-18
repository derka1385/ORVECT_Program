from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import active_garage_id
from app.database.session import get_db
from . import service

router = APIRouter(prefix="/api/vehicle-knowledge", tags=["vehicle-knowledge"])


class LookupInput(BaseModel):
    vin: str | None = Field(default=None, max_length=24)
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=120)
    model_year: int | None = Field(default=None, ge=1886, le=2100)
    engine_code: str | None = Field(default=None, max_length=60)
    dtc_codes: list[str] = Field(default_factory=list, max_length=30)
    symptoms: str = Field(default="", max_length=2000)


@router.post("/lookup")
def lookup(data: LookupInput, db: Session = Depends(get_db), gid: str = Depends(active_garage_id)):
    """Generation and engine variant as homologated, plus problems already reported on them.

    POST so the VIN never appears in a URL or an access log; only its first 11 characters are compared.
    """
    generation, variant, basis = service.resolve(db, data.make, data.model, data.model_year, data.engine_code, data.vin)
    vehicle = data.model_dump(exclude={"vin", "dtc_codes", "symptoms"})
    issues = service.find_issues(db, vehicle, generation, variant, data.dtc_codes, data.symptoms, limit=20)
    reference = service.vehicle_reference(generation, variant)
    if reference:
        reference["match_basis"] = basis
    return {"vehicle_reference": reference, "reported_issues": issues,
            "notice": "Pannes signalées dans le monde réel (rappels, bulletins, presse, forums) : à vérifier sur le véhicule, jamais une preuve."}
