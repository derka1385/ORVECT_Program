import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import DiagnosticTroubleCode, KnowledgeSource


DTC_PATTERN = re.compile(r"[PBCU][0-9A-F]{4}")
DTC_CATEGORY = {"P": "powertrain", "B": "body", "C": "chassis", "U": "network"}
UNAVAILABLE_DEFINITION = "Definition unavailable for this vehicle configuration."
DefinitionType = Literal["generic_standardized", "manufacturer_specific", "unknown"]


@dataclass(frozen=True)
class DTCDefinition:
    code: str
    category: str
    definition_type: DefinitionType
    description: str
    documented: bool
    source: dict | None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "category": self.category,
            "definition_type": self.definition_type,
            "manufacturer_specific": self.definition_type == "manufacturer_specific",
            "generic_description": self.description,
            "documented": self.documented,
            "source": self.source,
        }


def normalize_dtc(code: str) -> str | None:
    normalized = (code or "").strip().upper()
    return normalized if DTC_PATTERN.fullmatch(normalized) else None


def structurally_manufacturer_specific(code: str) -> bool:
    """Classify only ranges that are unambiguously manufacturer-controlled.

    Mixed/reserved ranges remain unknown unless an exact, compatible source exists.
    """
    return code[1] == "1" or (code[0] in {"B", "C", "U"} and code[1] == "2")


def source_reference(source: KnowledgeSource, compatibility: dict) -> dict:
    timestamp = source.updated_at or source.created_at or source.publication_date
    if not timestamp:
        raise ValueError(f"Knowledge source {source.id} is missing its required timestamp")
    return {
        "source_id": source.id,
        "source_type": source.source_type,
        "source_version": source.version,
        "vehicle_compatibility": compatibility,
        "timestamp": timestamp.isoformat() if timestamp else None,
        "verified": source.review_status == "reviewed",
    }


def resolve_dtc(db: Session, code: str, vehicle: dict | None = None) -> DTCDefinition | None:
    normalized = normalize_dtc(code)
    if not normalized:
        return None
    if structurally_manufacturer_specific(normalized):
        return DTCDefinition(normalized, DTC_CATEGORY[normalized[0]], "manufacturer_specific", UNAVAILABLE_DEFINITION, False, None)
    row = db.scalar(
        select(DiagnosticTroubleCode).where(
            DiagnosticTroubleCode.code == normalized,
            DiagnosticTroubleCode.definition_type == "generic_standardized",
            DiagnosticTroubleCode.confidence_tier.in_(["generic_standard", "demo_verified"]),
        )
    )
    if row and row.generic_description and row.source_id:
        source = db.get(KnowledgeSource, row.source_id)
        if source:
            compatibility = {"scope": "generic_standardized", "vehicle_id": (vehicle or {}).get("vehicle_id")}
            return DTCDefinition(
                normalized,
                row.category,
                "generic_standardized",
                row.generic_description,
                True,
                source_reference(source, compatibility),
            )
    kind: DefinitionType = "manufacturer_specific" if structurally_manufacturer_specific(normalized) else "unknown"
    return DTCDefinition(normalized, DTC_CATEGORY[normalized[0]], kind, UNAVAILABLE_DEFINITION, False, None)
