import json
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    DiagnosticImage,
    DiagnosticObservation,
    DiagnosticSession,
    DiagnosticStep,
    DiagnosticTroubleCode,
    KnowledgeItem,
    KnowledgeSource,
    VehicleConfiguration,
)
from app.modules.diagnostic_data.resolver import DiagnosticDataResolver, build_vehicle_context
from app.modules.dtc.service import source_reference


class TechnicalKnowledgeRetriever(Protocol):
    def search(self, db: Session, vehicle: dict, fault_codes: list[str], symptoms: str, query: str) -> list[dict]: ...


def _scope_is_compatible(scope: dict, vehicle: dict) -> bool:
    if not scope:
        return False
    if scope.get("scope") == "generic_standardized":
        return True
    comparisons = {
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "engine_code": vehicle.get("engine_code"),
        "market": vehicle.get("market"),
    }
    for field, actual in comparisons.items():
        expected = scope.get(field)
        if expected and (not actual or str(expected).casefold() != str(actual).casefold()):
            return False
    year = vehicle.get("model_year")
    if scope.get("year_from") and (not year or year < scope["year_from"]):
        return False
    if scope.get("year_to") and (not year or year > scope["year_to"]):
        return False
    return bool(scope.get("make") and scope.get("model") and scope.get("engine_code"))


class LocalKnowledgeRetriever:
    def search(self, db, vehicle, fault_codes, symptoms, query):
        dtcs = db.scalars(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.code.in_(fault_codes))).all()
        ids = [row.id for row in dtcs]
        rows = (
            db.scalars(
                select(KnowledgeItem).where(
                    KnowledgeItem.dtc_id.in_(ids),
                    KnowledgeItem.human_verified.is_(True),
                )
            ).all()
            if ids
            else []
        )
        results = []
        for item in rows:
            scope = (item.structured_data or {}).get("compatibility_scope", {})
            source = db.get(KnowledgeSource, item.source_id)
            if not source or source.review_status != "reviewed" or not _scope_is_compatible(scope, vehicle):
                continue
            results.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "excerpt": item.content[:1200],
                    "vehicle_scope": scope,
                    "source": source_reference(source, scope),
                }
            )
        return results[:20]


def _text(value, limit):
    return str(value or "").replace("\x00", "")[:limit]


class DiagnosticContextBuilder:
    def __init__(self, retriever=None):
        self.retriever = retriever or LocalKnowledgeRetriever()
        self.diagnostic_data_resolver = DiagnosticDataResolver()

    def build(self, db: Session, case: DiagnosticSession) -> tuple[dict, list[DiagnosticImage]]:
        config = db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id == case.vehicle_profile_id))
        vehicle = case.vehicle
        normalized = {
            "vehicle_id": vehicle.id,
            "make": config.make if config and config.make else vehicle.make,
            "model": config.model if config and config.model else vehicle.model,
            "generation": config.generation if config else None,
            "variant": config.type_variant_version if config else None,
            "vehicle_platform": config.platform if config else None,
            "model_year": config.model_year if config and config.model_year else vehicle.year,
            "market": config.market if config and config.market else vehicle.market,
            "engine_name": config.engine_name if config and config.engine_name else vehicle.engine_name,
            "engine_code": (config.engine_code_confirmed_by_user or config.engine_code) if config else (vehicle.engine_code if vehicle.engine_code != "UNKNOWN" else None),
            "engine_family": config.engine_family if config else None,
            "engine_displacement_cc": config.engine_displacement_cc if config else None,
            "engine_power_hp": config.engine_power_hp if config else None,
            "fuel_type": config.fuel_type if config and config.fuel_type else vehicle.fuel_type,
            "emission_standard": config.emission_standard if config else None,
            "transmission_type": config.transmission_type if config and config.transmission_type else vehicle.transmission,
            "transmission_code": config.transmission_code if config else None,
            "transmission_gears": config.transmission_gears if config else None,
            "drivetrain": config.drivetrain if config else None,
            "engine_ecu_manufacturer": config.engine_ecu_manufacturer if config else None,
            "engine_ecu_model": config.engine_ecu_model if config else None,
            "tecdoc_k_type": config.tecdoc_k_type if config else None,
            "cnit": config.cnit if config else None,
            "identification_confidence": config.confidence_score if config else 0,
            "configuration_confirmed": bool(config and config.confirmed_by_user) or vehicle.is_demo_vehicle,
            "user_confirmed": bool(config and config.confirmed_by_user) or vehicle.is_demo_vehicle,
            "precision_level": config.precision_level if config else ("demo_fixture" if vehicle.is_demo_vehicle else "basic_vehicle"),
        }
        observations = db.scalars(
            select(DiagnosticObservation)
            .where(DiagnosticObservation.session_id == case.id)
            .order_by(DiagnosticObservation.created_at.desc())
        ).all()
        dtcs = [item for item in observations if item.observation_type == "DTC"]
        measurements = [item for item in observations if item.observation_type == "measurement"][:30]
        codes = [item.key for item in dtcs]
        definitions = []
        for observation in dtcs:
            code = observation.key
            observation_value = observation.value or {}
            namespace = observation_value.get("namespace") or "sae_obd2"
            resolution_context = build_vehicle_context(
                db,
                vehicle,
                observation_value.get("ecu"),
                observation_value.get("ecu_identifiers", []),
            )
            resolution = self.diagnostic_data_resolver.resolve(db, namespace, code, resolution_context)
            definitions.append(
                {
                    "namespace": namespace,
                    "code": resolution["code"],
                    "ecu": observation_value.get("ecu"),
                    "description": resolution["description"],
                    "definition_type": resolution["definition_type"],
                    "documented": resolution["documented"],
                    "source": resolution["source"],
                    "resolution_status": resolution["status"],
                    "missing_information": resolution["missing_information"],
                    "candidate_count": len(resolution["candidates"]),
                }
            )
        steps = db.scalars(
            select(DiagnosticStep)
            .where(DiagnosticStep.session_id == case.id, DiagnosticStep.status.in_(["completed", "blocked"]))
            .order_by(DiagnosticStep.step_order.desc())
        ).all()
        images = db.scalars(
            select(DiagnosticImage)
            .where(DiagnosticImage.session_id == case.id, DiagnosticImage.processing_status == "ready")
            .order_by(DiagnosticImage.created_at)
        ).all()
        context = {
            "vehicle": normalized,
            "fault_codes": [
                {
                    "code": item.key,
                    "namespace": (item.value or {}).get("namespace") or "sae_obd2",
                    "ecu": (item.value or {}).get("ecu"),
                    "ecu_identifiers": (item.value or {}).get("ecu_identifiers", []),
                    "status": (item.value or {}).get("status", "unknown"),
                    "freeze_frame": (item.value or {}).get("freeze_frame", {}),
                    "technician_verification": (item.value or {}).get("technician_verification", "unconfirmed"),
                    "technician_note": _text((item.value or {}).get("technician_note"), 500),
                }
                for item in dtcs
            ],
            "technical_definitions": definitions,
            "measurements": [
                {"name": item.key, "value": item.value, "unit": item.unit, "source": item.source}
                for item in measurements
            ],
            "previous_steps": [
                {
                    "order": item.step_order,
                    "title": item.title,
                    "result": item.result,
                    "diagnostic_effect": "none"
                    if (item.result or {}).get("state") in {"inconclusive", "unavailable", "invalid", "refused"}
                    else "informative",
                    "comment": _text(item.technician_comment, 500),
                }
                for item in steps[:10]
            ],
            "images": [
                {
                    "id": item.id,
                    "category": item.category,
                    "description": _text(item.description, 500),
                    "ocr": item.extraction_result,
                }
                for item in images
            ],
            "untrusted_user_data": {
                "symptoms": _text(case.observed_symptoms, 5000),
                "circumstances": _text(case.appearance_circumstances, 3000),
            },
            "cross_correlation_request": {
                "analyze_as_one_case": True,
                "dimensions": [
                    "shared_root_cause",
                    "dependency",
                    "cascade",
                    "contradiction",
                    "vehicle_compatibility",
                ],
                "instruction": "Correlate all confirmed DTCs, symptoms, measurements and technician observations together; never concatenate independent code explanations.",
            },
            "technical_excerpts": self.retriever.search(
                db, normalized, codes, case.observed_symptoms, "diagnostic controls"
            ),
        }
        return context, images

    @staticmethod
    def canonical(context):
        return json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
