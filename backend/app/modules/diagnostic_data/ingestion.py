import hashlib
import json
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    DiagnosticCodeAlias,
    DiagnosticDataset,
    DiagnosticDatasetEvent,
    DiagnosticDefinitionVariant,
    DiagnosticIdentifier,
    DiagnosticNamespace,
    KnowledgeSource,
)

from .normalization import normalize_identifier, normalize_namespace
from .schemas import AliasEndpoint, DiagnosticDatasetImport
from .admission import source_is_usable
from .conflicts import detect_conflicts


class DatasetIngestionError(ValueError):
    pass


class DatasetAdapterUnavailable(DatasetIngestionError):
    pass


class DiagnosticDatasetAdapter(Protocol):
    format_name: str

    def parse(self, payload: bytes) -> DiagnosticDatasetImport: ...


class StructuredJSONAdapter:
    format_name = "structured_json"

    def parse(self, payload: bytes) -> DiagnosticDatasetImport:
        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DatasetIngestionError("Invalid structured diagnostic JSON") from exc
        return DiagnosticDatasetImport.model_validate(decoded)


class SAEStructuredAdapter(StructuredJSONAdapter):
    format_name = "sae_structured"


class OEMStructuredAdapter(StructuredJSONAdapter):
    format_name = "oem_structured"


class ODXAdapter:
    format_name = "odx"

    def parse(self, payload: bytes) -> DiagnosticDatasetImport:
        raise DatasetAdapterUnavailable(
            "ODX is registered but no licensed, profile-specific parser is configured; import refused"
        )


class PDXAdapter:
    format_name = "pdx"

    def parse(self, payload: bytes) -> DiagnosticDatasetImport:
        raise DatasetAdapterUnavailable(
            "PDX is registered but no licensed, profile-specific parser is configured; import refused"
        )


ADAPTERS: dict[str, DiagnosticDatasetAdapter] = {
    adapter.format_name: adapter
    for adapter in (
        StructuredJSONAdapter(),
        SAEStructuredAdapter(),
        OEMStructuredAdapter(),
        ODXAdapter(),
        PDXAdapter(),
    )
}


def calculate_dataset_checksum(payload: DiagnosticDatasetImport | dict) -> str:
    value = payload.model_dump(mode="json") if isinstance(payload, DiagnosticDatasetImport) else json.loads(json.dumps(payload))
    value["dataset"] = dict(value["dataset"])
    value["dataset"].pop("content_checksum_sha256", None)
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _namespace(db: Session, item) -> DiagnosticNamespace:
    key = normalize_namespace(item.key)
    row = db.scalar(select(DiagnosticNamespace).where(DiagnosticNamespace.key == key))
    if row:
        immutable = (row.manufacturer, row.brand_group, row.code_system)
        incoming = (item.manufacturer, item.brand_group, item.code_system)
        if immutable != incoming:
            raise DatasetIngestionError("Namespace metadata conflicts with the existing namespace")
        return row
    row = DiagnosticNamespace(
        key=key,
        manufacturer=item.manufacturer,
        brand_group=item.brand_group,
        code_system=item.code_system,
        description=item.description,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _identifier(
    db: Session,
    namespace: DiagnosticNamespace,
    code: str,
    display: str,
    code_type: str,
    manufacturer_specific_code: str | None = None,
) -> DiagnosticIdentifier:
    normalized = normalize_identifier(code)
    row = db.scalar(
        select(DiagnosticIdentifier).where(
            DiagnosticIdentifier.namespace_id == namespace.id,
            DiagnosticIdentifier.normalized_code == normalized,
        )
    )
    if row:
        if (
            row.code_type != code_type
            or row.canonical_display_code != display
            or row.manufacturer_specific_code != manufacturer_specific_code
        ):
            raise DatasetIngestionError("Identifier metadata conflicts with an existing canonical identifier")
        return row
    row = DiagnosticIdentifier(
        namespace_id=namespace.id,
        normalized_code=normalized,
        canonical_display_code=display,
        code_type=code_type,
        manufacturer_specific_code=manufacturer_specific_code,
    )
    db.add(row)
    db.flush()
    return row


def _alias_endpoint(db: Session, endpoint: AliasEndpoint, primary: DiagnosticNamespace) -> DiagnosticIdentifier:
    namespace = db.scalar(
        select(DiagnosticNamespace).where(DiagnosticNamespace.key == normalize_namespace(endpoint.namespace))
    )
    if not namespace:
        if endpoint.namespace != primary.key:
            raise DatasetIngestionError(
                f"Alias target namespace '{endpoint.namespace}' must be registered before import"
            )
        namespace = primary
    return _identifier(
        db,
        namespace,
        endpoint.code,
        endpoint.canonical_display_code,
        endpoint.code_type,
        endpoint.code if endpoint.code_type == "manufacturer_specific" else None,
    )


def ingest_dataset(db: Session, payload: DiagnosticDatasetImport, imported_by_user_id: str) -> DiagnosticDataset:
    source = db.get(KnowledgeSource, payload.source_id)
    if not source:
        raise DatasetIngestionError("Knowledge source does not exist")
    if source.review_status in {"rejected", "outdated"}:
        raise DatasetIngestionError("Rejected or outdated sources cannot be imported")
    if not payload.dataset.legal_use_confirmed:
        raise DatasetIngestionError("Legal use must be explicitly confirmed before import")
    if not source_is_usable(db, source):
        raise DatasetIngestionError("Source content rights assessment does not permit ingestion")
    actual_checksum = calculate_dataset_checksum(payload)
    if actual_checksum != payload.dataset.content_checksum_sha256:
        raise DatasetIngestionError("Dataset checksum does not match the canonical payload")
    if payload.dataset.format in {"odx", "pdx"}:
        raise DatasetAdapterUnavailable(
            f"{payload.dataset.format.upper()} profile parser is not configured; no data was imported"
        )

    namespace = _namespace(db, payload.namespace)
    duplicate = db.scalar(
        select(DiagnosticDataset).where(
            DiagnosticDataset.namespace_id == namespace.id,
            DiagnosticDataset.name == payload.dataset.name,
            DiagnosticDataset.version == payload.dataset.version,
        )
    )
    if duplicate:
        if duplicate.checksum == actual_checksum and duplicate.source_id == source.id:
            return duplicate  # Idempotent, including revoked imports: never silently reactivate.
        raise DatasetIngestionError("This dataset version already exists with different content")
    if db.scalar(select(DiagnosticDataset).where(DiagnosticDataset.checksum == actual_checksum)):
        raise DatasetIngestionError("This exact dataset payload has already been imported")
    dataset = DiagnosticDataset(
        namespace_id=namespace.id,
        source_id=source.id,
        name=payload.dataset.name,
        version=payload.dataset.version,
        adapter_type=payload.dataset.format,
        checksum=actual_checksum,
        status="staged",
        legal_use_confirmed=True,
        documented_available_count=payload.dataset.documented_available_count,
        imported_definition_count=0,
        rejected_definition_count=0,
        imported_by_user_id=imported_by_user_id,
        dataset_metadata=payload.dataset.metadata,
    )
    db.add(dataset)
    db.flush()

    for item in payload.definitions:
        if item.source_version != source.version:
            raise DatasetIngestionError("Every definition source_version must match the registered source version")
        identifier = _identifier(
            db,
            namespace,
            item.code,
            item.canonical_display_code,
            item.code_type,
            item.manufacturer_specific_code or (item.code if item.code_type == "manufacturer_specific" else None),
        )
        scope = item.applicability.model_dump(mode="json")
        definition = DiagnosticDefinitionVariant(
                identifier_id=identifier.id,
                dataset_id=dataset.id,
                source_id=source.id,
                external_record_id=item.provenance.record_id,
                description=item.description,
                failure_mode=item.failure_mode,
                subtype=item.subtype,
                provenance=item.provenance.model_dump(mode="json"),
                source_version=item.source_version,
                verification_status="unreviewed",
                promotion_stage="quarantined",
                is_generated=item.origin == "generated",
                **scope,
            )
        db.add(definition)
        db.flush()
        detect_conflicts(db, definition)
        dataset.imported_definition_count += 1

    for item in payload.aliases:
        if item.source_version != source.version:
            raise DatasetIngestionError("Every alias source_version must match the registered source version")
        if item.source.namespace != namespace.key:
            raise DatasetIngestionError("Every alias source identifier must belong to the imported dataset namespace")
        source_identifier = _alias_endpoint(db, item.source, namespace)
        target_identifier = _alias_endpoint(db, item.target, namespace)
        db.add(
            DiagnosticCodeAlias(
                source_identifier_id=source_identifier.id,
                target_identifier_id=target_identifier.id,
                dataset_id=dataset.id,
                relationship_type=item.relationship_type,
                source_id=source.id,
                source_version=item.source_version,
                provenance=item.provenance.model_dump(mode="json"),
                verification_status="unreviewed",
                promotion_stage="quarantined",
                is_generated=item.origin == "generated",
            )
        )
    db.add(DiagnosticDatasetEvent(dataset_id=dataset.id, action="imported", actor_user_id=imported_by_user_id,
        reason="Versioned checksum-validated import; all records quarantined", details={"checksum": actual_checksum}))
    db.commit()
    return dataset
