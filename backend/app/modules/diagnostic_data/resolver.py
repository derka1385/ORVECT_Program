from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    DiagnosticCodeAlias,
    DiagnosticDataset,
    DiagnosticDefinitionVariant,
    DiagnosticIdentifier,
    DiagnosticNamespace,
    KnowledgeSource,
    VehicleConfiguration,
    VehicleProfile,
)
from app.modules.dtc.service import UNAVAILABLE_DEFINITION, resolve_dtc, source_reference

from .normalization import normalize_identifier, normalize_namespace, split_uds_display
from .admission import admission_error, rights_payload, source_is_usable
from .conflicts import open_conflicts


ResolutionStatus = Literal[
    "resolved",
    "ambiguous",
    "insufficient_vehicle_configuration",
    "definition_unavailable_for_vehicle_configuration",
    "unknown",
]


def build_vehicle_context(
    db: Session,
    vehicle: VehicleProfile,
    ecu_module: str | None = None,
    ecu_identifiers: list[str] | None = None,
) -> dict:
    config = db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id == vehicle.id))
    return {
        "manufacturer": config.manufacturer if config else vehicle.make,
        "brand": config.make if config and config.make else vehicle.make,
        "vehicle_platform": config.platform if config else None,
        "model": config.model if config and config.model else vehicle.model,
        "model_year": config.model_year if config and config.model_year else vehicle.year,
        "engine_code": (
            config.engine_code_confirmed_by_user or config.engine_code
            if config
            else (vehicle.engine_code if vehicle.engine_code != "UNKNOWN" else None)
        ),
        "transmission_code": config.transmission_code if config else None,
        "ecu_module": ecu_module,
        "ecu_identifiers": ecu_identifiers or [],
    }


def _same(expected, actual) -> bool:
    return str(expected).strip().casefold() == str(actual).strip().casefold()


def _scope(variant: DiagnosticDefinitionVariant) -> dict:
    return {
        "manufacturer": variant.manufacturer,
        "brand": variant.brand,
        "vehicle_platform": variant.vehicle_platform,
        "model": variant.model,
        "model_year_from": variant.model_year_from,
        "model_year_to": variant.model_year_to,
        "engine_code": variant.engine_code,
        "transmission_code": variant.transmission_code,
        "ecu_module": variant.ecu_module,
        "ecu_identifiers": variant.ecu_identifiers or [],
    }


@dataclass(frozen=True)
class Applicability:
    contradictory: bool
    missing_fields: tuple[str, ...]
    constraint_fields: frozenset[str]

    @property
    def specificity(self) -> int:
        return len(self.constraint_fields)


def _applicability(variant: DiagnosticDefinitionVariant, vehicle: dict) -> Applicability:
    missing: list[str] = []
    constraints: set[str] = set()
    if variant.subtype:
        constraints.add("failure_type")
        if not vehicle.get("failure_type"):
            missing.append("failure_type")
        elif not _same(variant.subtype, vehicle["failure_type"]):
            return Applicability(True, (), frozenset(constraints))
    for field in ("manufacturer", "brand", "vehicle_platform", "model", "engine_code", "transmission_code", "ecu_module"):
        expected = getattr(variant, field)
        if not expected:
            continue
        constraints.add(field)
        actual = vehicle.get(field)
        if actual is None or actual == "":
            missing.append(field)
        elif not _same(expected, actual):
            return Applicability(True, (), frozenset(constraints))

    if variant.model_year_from is not None or variant.model_year_to is not None:
        constraints.add("model_year")
        year = vehicle.get("model_year")
        if year is None:
            missing.append("model_year")
        elif (variant.model_year_from is not None and year < variant.model_year_from) or (
            variant.model_year_to is not None and year > variant.model_year_to
        ):
            return Applicability(True, (), frozenset(constraints))

    expected_ecu_ids = {str(value).strip().casefold() for value in (variant.ecu_identifiers or []) if value}
    if expected_ecu_ids:
        constraints.add("ecu_identifiers")
        actual_ecu_ids = {str(value).strip().casefold() for value in vehicle.get("ecu_identifiers", []) if value}
        if not actual_ecu_ids:
            missing.append("ecu_identifiers")
        elif expected_ecu_ids.isdisjoint(actual_ecu_ids):
            return Applicability(True, (), frozenset(constraints))
    return Applicability(False, tuple(dict.fromkeys(missing)), frozenset(constraints))


def _source_payload(source: KnowledgeSource, dataset: DiagnosticDataset, compatibility: dict) -> dict:
    return {
        **source_reference(source, compatibility),
        "licensing": {
            "license_type": source.license_type,
            "publisher": source.publisher,
            "legal_use_confirmed": dataset.legal_use_confirmed,
        },
        "dataset": {
            "dataset_id": dataset.id,
            "name": dataset.name,
            "version": dataset.version,
            "checksum": dataset.checksum,
        },
    }


def _llm_source(source_payload: dict) -> dict:
    return {key: source_payload[key] for key in (
        "source_id", "source_type", "source_version", "vehicle_compatibility", "timestamp", "verified"
    )}


class DiagnosticDataResolver:
    """Resolve identifiers only from exact production data; never synthesize a definition."""

    def _aliases(self, db: Session, identifier: DiagnosticIdentifier) -> list[dict]:
        rows = db.scalars(
            select(DiagnosticCodeAlias).where(
                DiagnosticCodeAlias.source_identifier_id == identifier.id,
                DiagnosticCodeAlias.promotion_stage == "production",
                DiagnosticCodeAlias.verification_status == "verified",
                DiagnosticCodeAlias.is_generated.is_(False),
            ).order_by(DiagnosticCodeAlias.source_version, DiagnosticCodeAlias.id)
        ).all()
        output = []
        for row in rows:
            target = db.get(DiagnosticIdentifier, row.target_identifier_id)
            namespace = db.get(DiagnosticNamespace, target.namespace_id) if target else None
            source = db.get(KnowledgeSource, row.source_id)
            dataset = db.get(DiagnosticDataset, row.dataset_id)
            if not target or not namespace or not namespace.is_active or not source or not dataset:
                continue
            if (
                source.review_status != "reviewed"
                or dataset.status != "active"
                or not dataset.legal_use_confirmed
                or dataset.source_id != row.source_id
                or dataset.namespace_id != identifier.namespace_id
                or row.source_version != source.version
                or admission_error(db, row)
            ):
                continue
            full_source = _source_payload(source, dataset, {"scope": "documented_code_alias"})
            full_source["rights_assessment"] = rights_payload(db, source)
            output.append(
                {
                    "relationship_type": row.relationship_type,
                    "namespace": namespace.key,
                    "code": target.normalized_code,
                    "canonical_display_code": target.canonical_display_code,
                    "source": full_source,
                    "provenance": row.provenance,
                }
            )
        collapsed = {}
        for item in output:
            key = (item["relationship_type"], item["namespace"], item["code"])
            evidence = {"source": item["source"], "provenance": item["provenance"]}
            if key not in collapsed:
                collapsed[key] = {**item, "evidence": []}
            collapsed[key]["evidence"].append(evidence)
        return [collapsed[key] for key in sorted(collapsed)]

    def _legacy_sae(self, db: Session, namespace: str, code: str, vehicle: dict) -> dict | None:
        if namespace != "sae_obd2":
            return None
        legacy = resolve_dtc(db, code, vehicle)
        if not legacy:
            return None
        source = db.get(KnowledgeSource, legacy.source["source_id"]) if legacy.source else None
        source_details = None
        if source and legacy.source:
            source_details = {
                **legacy.source,
                "licensing": {
                    "license_type": source.license_type,
                    "publisher": source.publisher,
                    "legal_use_confirmed": source_is_usable(db, source),
                    **rights_payload(db, source),
                },
                "dataset": {
                    "dataset_id": "legacy_dtcs",
                    "name": source.title,
                    "version": source.version,
                    "checksum": source.checksum,
                },
                "provenance": {
                    "source_url": source.source_url,
                    "local_file_path": source.local_file_path,
                    "checksum": source.checksum,
                },
            }
        return {
            "status": "resolved" if legacy.documented else "unknown",
            "namespace": namespace,
            "code": legacy.code,
            "canonical_display_code": legacy.code,
            "definition_type": legacy.definition_type,
            "documented": legacy.documented,
            "description": legacy.description,
            "source": legacy.source,
            "source_details": source_details,
            "candidates": [],
            "missing_information": [],
            "aliases": [],
            "generic_obd_equivalent": None,
        }

    def resolve(self, db: Session, namespace: str, code: str, vehicle: dict | None = None, _visited=None) -> dict:
        normalized_namespace = normalize_namespace(namespace)
        parsed = split_uds_display(code)
        normalized_code = parsed["code"]
        context = dict(vehicle or {})
        if parsed["failure_type"]:
            context["failure_type"] = parsed["failure_type"]
        visited = set(_visited or ()) | {(normalized_namespace, normalized_code)}
        namespace_row = db.scalar(
            select(DiagnosticNamespace).where(
                DiagnosticNamespace.key == normalized_namespace,
                DiagnosticNamespace.is_active.is_(True),
            )
        )
        identifier = None
        if namespace_row:
            identifier = db.scalar(
                select(DiagnosticIdentifier).where(
                    DiagnosticIdentifier.namespace_id == namespace_row.id,
                    DiagnosticIdentifier.normalized_code == normalized_code,
                )
            )
        if not identifier:
            legacy = self._legacy_sae(db, normalized_namespace, normalized_code, context)
            if legacy:
                return legacy
            definition_type = "manufacturer_specific" if namespace_row and namespace_row.manufacturer else "unknown"
            return {
                "status": "unknown",
                "namespace": normalized_namespace,
                "code": normalized_code,
                "canonical_display_code": normalized_code,
                "definition_type": definition_type,
                "documented": False,
                "description": UNAVAILABLE_DEFINITION,
                "source": None,
                "source_details": None,
                "candidates": [],
                "missing_information": [],
                "aliases": [],
                "generic_obd_equivalent": None,
            }

        rows = db.execute(
            select(DiagnosticDefinitionVariant, DiagnosticDataset, KnowledgeSource)
            .join(DiagnosticDataset, DiagnosticDataset.id == DiagnosticDefinitionVariant.dataset_id)
            .join(KnowledgeSource, KnowledgeSource.id == DiagnosticDefinitionVariant.source_id)
            .where(
                DiagnosticDefinitionVariant.identifier_id == identifier.id,
                DiagnosticDefinitionVariant.promotion_stage == "production",
                DiagnosticDefinitionVariant.verification_status == "verified",
                DiagnosticDefinitionVariant.is_generated.is_(False),
                DiagnosticDataset.status == "active",
                DiagnosticDataset.legal_use_confirmed.is_(True),
                DiagnosticDataset.namespace_id == identifier.namespace_id,
                DiagnosticDataset.source_id == DiagnosticDefinitionVariant.source_id,
                KnowledgeSource.review_status == "reviewed",
                DiagnosticDefinitionVariant.source_version == KnowledgeSource.version,
            )
        ).all()
        if not rows:
            legacy = self._legacy_sae(db, normalized_namespace, normalized_code, context)
            if legacy:
                return legacy
        plausible: list[tuple[dict, Applicability]] = []
        for variant, dataset, source in rows:
            if admission_error(db, variant):
                continue
            match = _applicability(variant, context)
            if match.contradictory:
                continue
            compatibility = _scope(variant)
            full_source = _source_payload(source, dataset, compatibility)
            full_source["rights_assessment"] = rights_payload(db, source)
            candidate = {
                "definition_id": variant.id,
                "namespace": normalized_namespace,
                "code": identifier.normalized_code,
                "canonical_display_code": identifier.canonical_display_code,
                "definition_type": identifier.code_type,
                "manufacturer_specific_code": identifier.manufacturer_specific_code,
                "description": variant.description,
                "failure_mode": variant.failure_mode,
                "subtype": variant.subtype,
                "applicability": compatibility,
                "missing_fields": list(match.missing_fields),
                "specificity": match.specificity,
                "source": full_source,
                "provenance": variant.provenance,
                "source_version": variant.source_version,
                "verification_status": variant.verification_status,
            }
            plausible.append((candidate, match))

        aliases = self._aliases(db, identifier)
        generic_targets = [
                {"namespace": item["namespace"], "code": item["code"], "canonical_display_code": item["canonical_display_code"]}
                for item in aliases
                if item["relationship_type"] == "generic_obd_equivalent"
        ]
        generic = generic_targets[0] if len(generic_targets) == 1 else None
        base = {
            "namespace": normalized_namespace,
            "code": identifier.normalized_code,
            "canonical_display_code": identifier.canonical_display_code,
            "definition_type": identifier.code_type,
            "aliases": aliases,
            "generic_obd_equivalent": generic,
        }
        conflicts = open_conflicts(db, identifier.id)
        if conflicts:
            return {**base, "status": "ambiguous", "documented": False,
                "description": UNAVAILABLE_DEFINITION, "source": None, "source_details": None,
                "candidates": [], "missing_information": [],
                "conflict_ids": [row.id for row in conflicts], "reason": "unresolved_source_conflict"}
        if not plausible:
            # Only explicitly evidenced alias edges are traversed; never infer a
            # numeric conversion. Cycles terminate and competing targets abstain.
            targets = []
            if len(visited) < 8:
                for alias in aliases:
                    key = (alias["namespace"], alias["code"])
                    if key not in visited:
                        target = self.resolve(db, *key, context, _visited=visited)
                        if target["status"] == "resolved":
                            targets.append((alias, target))
            if len(targets) == 1:
                alias, target = targets[0]
                return {**target, **base, "resolved_via_alias": {"namespace": alias["namespace"], "code": alias["code"], "source": alias["source"]}}
            if len(targets) > 1:
                return {**base, "status": "ambiguous", "documented": False, "description": UNAVAILABLE_DEFINITION,
                    "source": None, "source_details": None, "candidates": [], "missing_information": []}
            if identifier.code_type == "generic_standardized":
                legacy = self._legacy_sae(db, normalized_namespace, normalized_code, context)
                if legacy and legacy["documented"]:
                    return legacy
            return {
                **base,
                "status": "definition_unavailable_for_vehicle_configuration" if rows else "unknown",
                "documented": False,
                "description": UNAVAILABLE_DEFINITION,
                "source": None,
                "source_details": None,
                "candidates": [],
                "missing_information": [],
            }

        plausible.sort(key=lambda item: item[1].specificity, reverse=True)
        top = [
            item
            for item in plausible
            if not any(
                other[1].constraint_fields > item[1].constraint_fields
                for other in plausible
            )
        ]
        missing = sorted({field for _, match in top for field in match.missing_fields})
        candidates = [candidate for candidate, _ in plausible]
        if missing:
            return {
                **base,
                "status": "insufficient_vehicle_configuration",
                "documented": False,
                "description": UNAVAILABLE_DEFINITION,
                "source": None,
                "source_details": None,
                "candidates": candidates,
                "missing_information": missing,
            }
        if len(top) > 1:
            # Agreement from independent sources is multiple evidence, not
            # multiple meanings. Only exact normalized semantic/scope equality
            # collapses; differences still require explicit conflict review.
            meanings = {(candidate["description"].strip().casefold(), candidate["failure_mode"], candidate["subtype"],
                str(sorted(candidate["applicability"].items()))) for candidate, _ in top}
            if len(meanings) == 1:
                top.sort(key=lambda pair: pair[0]["definition_id"])
                top[0][0]["source"]["corroborating_sources"] = [candidate["source"] for candidate, _ in top[1:]]
                top = top[:1]
        if len(top) > 1:
            return {
                **base,
                "status": "ambiguous",
                "documented": False,
                "description": UNAVAILABLE_DEFINITION,
                "source": None,
                "source_details": None,
                "candidates": [candidate for candidate, _ in top],
                "missing_information": [],
            }
        selected = top[0][0]
        return {
            **base,
            "status": "resolved",
            "documented": True,
            "description": selected["description"],
            "source": _llm_source(selected["source"]),
            "source_details": selected["source"],
            "candidates": [selected],
            "missing_information": [],
        }
