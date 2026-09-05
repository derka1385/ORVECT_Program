from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database.models import (
    DiagnosticCodeAlias,
    DiagnosticDataset,
    DiagnosticDefinitionVariant,
    DiagnosticIdentifier,
    DiagnosticNamespace,
    DiagnosticTroubleCode,
    KnowledgeSource,
)
from .admission import admission_error
from .conflicts import open_conflicts


GROUP_COLUMNS = {
    "namespace": DiagnosticNamespace.key,
    "manufacturer": DiagnosticDefinitionVariant.manufacturer,
    "brand": DiagnosticDefinitionVariant.brand,
    "ecu_module": DiagnosticDefinitionVariant.ecu_module,
    "code_type": DiagnosticIdentifier.code_type,
}


def coverage_report(db: Session, group_by: str = "namespace") -> dict:
    if group_by not in GROUP_COLUMNS:
        raise ValueError("Unsupported coverage grouping")
    group = GROUP_COLUMNS[group_by]
    eligible_definitions = eligible_records(db, DiagnosticDefinitionVariant)
    eligible_aliases = eligible_records(db, DiagnosticCodeAlias)
    eligible_definition_ids = [row.id for row in eligible_definitions]
    eligible_alias_ids = [row.id for row in eligible_aliases]
    statement = (
        select(
            group.label("group"),
            func.count(DiagnosticDefinitionVariant.id).label("documented_available"),
            func.sum(
                case(
                    (
                        (DiagnosticDefinitionVariant.promotion_stage == "production")
                        & (DiagnosticDefinitionVariant.verification_status == "verified")
                        & DiagnosticDefinitionVariant.is_generated.is_(False)
                        & (DiagnosticDataset.status == "active")
                        & DiagnosticDataset.legal_use_confirmed.is_(True)
                        & (DiagnosticDataset.namespace_id == DiagnosticIdentifier.namespace_id)
                        & (DiagnosticDataset.source_id == DiagnosticDefinitionVariant.source_id)
                        & (KnowledgeSource.review_status == "reviewed")
                        & (DiagnosticDefinitionVariant.source_version == KnowledgeSource.version),
                        case((DiagnosticDefinitionVariant.id.in_(eligible_definition_ids), 1), else_=0),
                    ),
                    else_=0,
                )
            ).label("production"),
            func.sum(case((DiagnosticDefinitionVariant.promotion_stage == "verified", 1), else_=0)).label(
                "verified_not_production"
            ),
            func.sum(
                case(
                    (DiagnosticDefinitionVariant.promotion_stage.in_(["quarantined", "source_matched"]), 1),
                    else_=0,
                )
            ).label("unreviewed"),
            func.sum(case((DiagnosticDefinitionVariant.is_generated.is_(True), 1), else_=0)).label(
                "generated_quarantined"
            ),
        )
        .join(DiagnosticIdentifier, DiagnosticIdentifier.id == DiagnosticDefinitionVariant.identifier_id)
        .join(DiagnosticNamespace, DiagnosticNamespace.id == DiagnosticIdentifier.namespace_id)
        .join(DiagnosticDataset, DiagnosticDataset.id == DiagnosticDefinitionVariant.dataset_id)
        .join(KnowledgeSource, KnowledgeSource.id == DiagnosticDefinitionVariant.source_id)
        .group_by(group)
        .order_by(group)
    )
    rows = []
    for row in db.execute(statement).mappings():
        available = int(row["documented_available"] or 0)
        production = int(row["production"] or 0)
        rows.append(
            {
                "group": row["group"] or "unspecified",
                "documented_available": available,
                "covered": production,
                "production": production,
                "verified_not_production": int(row["verified_not_production"] or 0),
                "unreviewed": int(row["unreviewed"] or 0),
                "generated_quarantined": int(row["generated_quarantined"] or 0),
                "legacy_active_unreviewed": 0,
                "unavailable": None,
                "coverage_ratio": production / available if available else None,
                "denominator_basis": "documented records imported from the declared source corpus",
            }
        )

    if group_by == "namespace":
        unavailable_by_namespace = {
            key: int(unavailable or 0)
            for key, unavailable in db.execute(
                select(
                    DiagnosticNamespace.key,
                    func.sum(
                        DiagnosticDataset.documented_available_count
                        - DiagnosticDataset.imported_definition_count
                    ),
                )
                .join(DiagnosticDataset, DiagnosticDataset.namespace_id == DiagnosticNamespace.id)
                .group_by(DiagnosticNamespace.key)
            ).all()
        }
        known = {row["group"] for row in rows}
        for row in rows:
            row["unavailable"] = max(unavailable_by_namespace.get(row["group"], 0), 0)
            row["documented_available"] += row["unavailable"]
            row["coverage_ratio"] = (
                row["production"] / row["documented_available"] if row["documented_available"] else None
            )
            row["denominator_basis"] = "documented_available_count declared by imported source manifests"
        for namespace, unavailable in unavailable_by_namespace.items():
            if namespace not in known:
                rows.append(
                    {
                        "group": namespace,
                        "documented_available": unavailable,
                        "covered": 0,
                        "production": 0,
                        "verified_not_production": 0,
                        "unreviewed": 0,
                        "generated_quarantined": 0,
                        "legacy_active_unreviewed": 0,
                        "unavailable": unavailable,
                        "coverage_ratio": 0.0 if unavailable else None,
                        "denominator_basis": "documented_available_count declared by imported source manifests",
                    }
                )
                known.add(namespace)
        for namespace in db.scalars(select(DiagnosticNamespace.key).order_by(DiagnosticNamespace.key)).all():
            if namespace not in known:
                rows.append(
                    {
                        "group": namespace,
                        "documented_available": 0,
                        "covered": 0,
                        "production": 0,
                        "verified_not_production": 0,
                        "unreviewed": 0,
                        "generated_quarantined": 0,
                        "legacy_active_unreviewed": 0,
                        "unavailable": 0,
                        "coverage_ratio": None,
                        "denominator_basis": "no diagnostic source corpus imported",
                    }
                )

    legacy_count = db.scalar(
        select(func.count()).select_from(DiagnosticTroubleCode).where(
            DiagnosticTroubleCode.definition_type == "generic_standardized",
            DiagnosticTroubleCode.confidence_tier.in_(["generic_standard", "demo_verified"]),
            DiagnosticTroubleCode.generic_description != "",
            DiagnosticTroubleCode.source_id.is_not(None),
        )
    ) or 0
    legacy_group = "sae_obd2" if group_by == "namespace" else "generic_standardized" if group_by == "code_type" else None
    if legacy_group and legacy_count:
        row = next((item for item in rows if item["group"] == legacy_group), None)
        if not row:
            row = {
                "group": legacy_group,
                "documented_available": 0,
                "covered": 0,
                "production": 0,
                "verified_not_production": 0,
                "unreviewed": 0,
                "generated_quarantined": 0,
                "legacy_active_unreviewed": 0,
                "unavailable": 0 if group_by == "namespace" else None,
                "coverage_ratio": None,
                "denominator_basis": "active legacy generic source corpus plus versioned dataset manifests",
            }
            rows.append(row)
        row["documented_available"] += legacy_count
        row["covered"] += legacy_count
        row["unreviewed"] += legacy_count
        row["legacy_active_unreviewed"] += legacy_count
        row["coverage_ratio"] = row["covered"] / row["documented_available"]
        row["denominator_basis"] = "active legacy generic source corpus plus versioned dataset manifests"

    vag_ids = set(
        db.scalars(
            select(DiagnosticIdentifier.id)
            .join(DiagnosticNamespace, DiagnosticNamespace.id == DiagnosticIdentifier.namespace_id)
            .join(DiagnosticDefinitionVariant, DiagnosticDefinitionVariant.identifier_id == DiagnosticIdentifier.id)
            .join(DiagnosticDataset, DiagnosticDataset.id == DiagnosticDefinitionVariant.dataset_id)
            .join(KnowledgeSource, KnowledgeSource.id == DiagnosticDefinitionVariant.source_id)
            .where(
                func.lower(DiagnosticNamespace.brand_group) == "vag",
                DiagnosticIdentifier.code_type == "manufacturer_specific",
                DiagnosticDefinitionVariant.promotion_stage == "production",
                DiagnosticDefinitionVariant.verification_status == "verified",
                DiagnosticDefinitionVariant.is_generated.is_(False),
                DiagnosticDataset.status == "active",
                DiagnosticDataset.legal_use_confirmed.is_(True),
                DiagnosticDataset.namespace_id == DiagnosticIdentifier.namespace_id,
                DiagnosticDataset.source_id == DiagnosticDefinitionVariant.source_id,
                KnowledgeSource.review_status == "reviewed",
                DiagnosticDefinitionVariant.source_version == KnowledgeSource.version,
                DiagnosticDefinitionVariant.id.in_(eligible_definition_ids),
            )
            .distinct()
        ).all()
    )
    aliased_vag_ids = set(
        db.scalars(
            select(DiagnosticCodeAlias.source_identifier_id).where(
                DiagnosticCodeAlias.source_identifier_id.in_(vag_ids),
                DiagnosticCodeAlias.relationship_type == "generic_obd_equivalent",
                DiagnosticCodeAlias.promotion_stage == "production",
                DiagnosticCodeAlias.verification_status == "verified",
                DiagnosticCodeAlias.is_generated.is_(False),
                DiagnosticCodeAlias.id.in_(eligible_alias_ids),
            )
            .join(DiagnosticIdentifier, DiagnosticIdentifier.id == DiagnosticCodeAlias.source_identifier_id)
            .join(DiagnosticDataset, DiagnosticDataset.id == DiagnosticCodeAlias.dataset_id)
            .join(KnowledgeSource, KnowledgeSource.id == DiagnosticCodeAlias.source_id)
            .where(
                DiagnosticDataset.status == "active",
                DiagnosticDataset.legal_use_confirmed.is_(True),
                DiagnosticDataset.namespace_id == DiagnosticIdentifier.namespace_id,
                DiagnosticDataset.source_id == DiagnosticCodeAlias.source_id,
                KnowledgeSource.review_status == "reviewed",
                DiagnosticCodeAlias.source_version == KnowledgeSource.version,
            )
        ).all()
    ) if vag_ids else set()
    return {
        "metric": "documented DTC definitions covered by the resolver / documented definitions available in imported corpus",
        "group_by": group_by,
        "items": rows,
        "vag": {
            "production_manufacturer_identifiers": len(vag_ids),
            "with_documented_generic_obd_equivalent": len(aliased_vag_ids),
            "without_generic_obd_equivalent": len(vag_ids - aliased_vag_ids),
        },
        "summary": catalogue_summary(db, eligible_definitions, eligible_aliases, legacy_count),
    }


def eligible_records(db, model):
    rows = db.scalars(select(model).join(DiagnosticDataset, DiagnosticDataset.id == model.dataset_id).where(
        model.promotion_stage == "production", model.verification_status == "verified",
        model.is_generated.is_(False), DiagnosticDataset.status == "active",
        DiagnosticDataset.legal_use_confirmed.is_(True), DiagnosticDataset.source_id == model.source_id,
    )).all()
    result = []
    for row in rows:
        identifier_id = row.identifier_id if model is DiagnosticDefinitionVariant else row.source_identifier_id
        identifier = db.get(DiagnosticIdentifier, identifier_id)
        source = db.get(KnowledgeSource, row.source_id)
        dataset = db.get(DiagnosticDataset, row.dataset_id)
        namespace = db.get(DiagnosticNamespace, identifier.namespace_id)
        if (not namespace.is_active or dataset.namespace_id != identifier.namespace_id
                or row.source_version != source.version or admission_error(db, row)
                or open_conflicts(db, identifier_id)):
            continue
        result.append(row)
    return result


def catalogue_summary(db, definitions, aliases, legacy_count):
    identifiers = {row.id: row for row in db.scalars(select(DiagnosticIdentifier)).all()}
    namespaces = {row.id: row for row in db.scalars(select(DiagnosticNamespace)).all()}
    parent = {key: key for key in identifiers}
    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key
    edges = set()
    for row in aliases:
        a, b = sorted((row.source_identifier_id, row.target_identifier_id))
        edges.add((a, b))
        parent[root(b)] = root(a)
    resolved_roots = {root(row.identifier_id) for row in definitions}
    legacy_codes = set(db.scalars(select(DiagnosticTroubleCode.code).where(
        DiagnosticTroubleCode.definition_type == "generic_standardized",
        DiagnosticTroubleCode.source_id.is_not(None), DiagnosticTroubleCode.generic_description != "",
        DiagnosticTroubleCode.confidence_tier.in_(["generic_standard", "demo_verified"]),
    )).all())
    resolved_roots.update(root(key) for key, row in identifiers.items()
        if namespaces[row.namespace_id].key == "sae_obd2" and row.normalized_code in legacy_codes)
    stages = {stage: 0 for stage in ("candidate", "quarantined", "source_matched", "verified", "production")}
    for stage, count in db.execute(select(DiagnosticDefinitionVariant.promotion_stage, func.count()).group_by(DiagnosticDefinitionVariant.promotion_stage)):
        stages[stage] = count
    brands = {brand: 0 for brand in ("Volkswagen", "Audi", "Škoda", "SEAT", "CUPRA", "Volkswagen Commercial Vehicles")}
    modules = {module: 0 for module in ("engine", "transmission", "ABS/ESP", "airbag", "gateway", "central electronics", "immobilizer/access", "infotainment", "HVAC", "parking brake", "ADAS")}
    by_namespace = {row.key: 0 for row in namespaces.values()}
    for row in definitions:
        by_namespace[namespaces[identifiers[row.identifier_id].namespace_id].key] += 1
        brands[row.brand or "unspecified"] = brands.get(row.brand or "unspecified", 0) + 1
        modules[row.ecu_module or "unspecified"] = modules.get(row.ecu_module or "unspecified", 0) + 1
    return {"active_total": legacy_count + len(definitions), "legacy_generic_active_unreviewed": legacy_count,
        "production_definition_rows": len(definitions), "production_base_concepts": len({root(r.identifier_id) for r in definitions}),
        "production_generic_definition_rows": sum(identifiers[r.identifier_id].code_type == "generic_standardized" for r in definitions),
        "production_vag_definition_rows": sum((namespaces[identifiers[r.identifier_id].namespace_id].brand_group or "").casefold() == "vag" for r in definitions),
        "production_alias_evidence_rows": len(aliases), "distinct_alias_edges": len(edges),
        "unresolved_identifiers": sum(root(key) not in resolved_roots for key in identifiers),
        "ecu_context_definition_rows": sum(bool(r.ecu_module or r.ecu_identifiers) for r in definitions),
        "lifecycle_definition_rows": stages, "by_namespace": by_namespace, "by_brand": brands, "by_module": modules,
        "counting_note": "Definition rows are contextual source records, not deduplicated concepts. Legacy generic rows are active/unreviewed, not verified production. Archived quarantine is reported separately."}
