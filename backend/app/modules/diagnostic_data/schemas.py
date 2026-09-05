from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .normalization import normalize_identifier, normalize_namespace, split_uds_display


CodeType = Literal["generic_standardized", "manufacturer_specific"]
PromotionStage = Literal["quarantined", "source_matched", "verified", "production"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NamespaceInput(Strict):
    key: str
    manufacturer: str | None = Field(default=None, max_length=120)
    brand_group: str | None = Field(default=None, max_length=120)
    code_system: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)

    @field_validator("key")
    @classmethod
    def valid_key(cls, value):
        return normalize_namespace(value)


class DatasetInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    format: Literal["structured_json", "odx", "pdx", "sae_structured", "oem_structured"]
    legal_use_confirmed: bool
    documented_available_count: int = Field(ge=0)
    content_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata: dict = Field(default_factory=dict)


class ProvenanceInput(Strict):
    record_id: str = Field(min_length=1, max_length=160)
    document_reference: str = Field(min_length=1, max_length=500)
    section: str | None = Field(default=None, max_length=300)
    retrieved_at: datetime
    legacy_quarantine_entry_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    admission_tier: Literal["A", "B", "C"] | None = None
    claims: dict[str, list["ClaimEvidenceInput"]] = Field(default_factory=dict)
    source_language: str | None = Field(default=None, max_length=20)
    normalization_method: Literal["verbatim", "human_normalized"] = "verbatim"


class ClaimEvidenceInput(Strict):
    source_id: str = Field(min_length=1, max_length=36)
    source_version: str = Field(min_length=1, max_length=80)
    document_reference: str = Field(min_length=1, max_length=500)
    assertion_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confidence: Literal["unverified", "supported"] = "unverified"


class SourceAssessmentInput(Strict):
    source_version: str = Field(min_length=1, max_length=80)
    category: Literal["licensed_oem", "licensed_standard", "open_data", "open_source_uncertain_underlying_rights", "research_only_proprietary", "unknown_licence"]
    authority_level: Literal["authoritative", "credible", "corroborative", "unknown"]
    commercial_use: Literal["allowed", "prohibited", "uncertain"]
    redistribution: Literal["allowed", "attribution", "share_alike", "prohibited", "uncertain"]
    attribution_requirements: str = Field(min_length=1, max_length=4000)
    licence_evidence: str = Field(min_length=1, max_length=4000)
    provenance_notes: str = Field(min_length=1, max_length=4000)
    independent_origin: str = Field(min_length=1, max_length=200)
    content_rights_confirmed: bool = False
    status: Literal["pending", "approved", "rejected"] = "pending"


class DatasetActionInput(Strict):
    reason: str = Field(min_length=10, max_length=500)


class ConflictResolutionInput(DatasetActionInput):
    # Definitions cannot be selected by this endpoint. Reject/revoke a dataset
    # first, or attest that the apparent conflict was not a semantic conflict.
    status: Literal["resolved_by_revocation", "not_a_conflict"]


class ApplicabilityInput(Strict):
    manufacturer: str | None = Field(default=None, max_length=120)
    brand: str | None = Field(default=None, max_length=120)
    vehicle_platform: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    model_year_from: int | None = Field(default=None, ge=1886, le=2200)
    model_year_to: int | None = Field(default=None, ge=1886, le=2200)
    engine_code: str | None = Field(default=None, max_length=100)
    transmission_code: str | None = Field(default=None, max_length=100)
    ecu_module: str | None = Field(default=None, max_length=120)
    ecu_identifiers: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def valid_year_range(self):
        if self.model_year_from and self.model_year_to and self.model_year_from > self.model_year_to:
            raise ValueError("model_year_from must be before model_year_to")
        return self


class DefinitionInput(Strict):
    code: str
    canonical_display_code: str = Field(min_length=1, max_length=100)
    code_type: CodeType
    manufacturer_specific_code: str | None = Field(default=None, max_length=100)
    description: str = Field(min_length=1, max_length=4000)
    failure_mode: str | None = Field(default=None, max_length=200)
    subtype: str | None = Field(default=None, max_length=160)
    applicability: ApplicabilityInput = Field(default_factory=ApplicabilityInput)
    provenance: ProvenanceInput
    source_version: str = Field(min_length=1, max_length=40)
    origin: Literal["source_extract", "manual_transcription", "generated"] = "source_extract"

    @model_validator(mode="before")
    @classmethod
    def separate_uds_identity(cls, value):
        value = dict(value)
        parsed = split_uds_display(value.get("code", ""))
        if parsed["status_byte"] is not None:
            raise ValueError("Transient DTC status belongs to an observation, never a definition")
        if parsed["failure_type"]:
            if value.get("subtype") not in (None, parsed["failure_type"]):
                raise ValueError("Conflicting failure subtype")
            value["code"] = parsed["code"]
            value["subtype"] = parsed["failure_type"]
            value["canonical_display_code"] = parsed["code"]
            if value.get("code_type") == "manufacturer_specific":
                value["manufacturer_specific_code"] = parsed["code"]
        return value

    @field_validator("code")
    @classmethod
    def valid_code(cls, value):
        return normalize_identifier(value)


class AliasEndpoint(Strict):
    namespace: str
    code: str
    canonical_display_code: str = Field(min_length=1, max_length=100)
    code_type: CodeType

    @field_validator("namespace")
    @classmethod
    def valid_namespace(cls, value):
        return normalize_namespace(value)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value):
        if split_uds_display(value)["failure_type"]:
            raise ValueError("Alias endpoints must reference base identities; subtype/status are not separate concepts")
        return normalize_identifier(value)


class AliasInput(Strict):
    source: AliasEndpoint
    target: AliasEndpoint
    relationship_type: Literal["generic_obd_equivalent", "documented_alias"]
    provenance: ProvenanceInput
    source_version: str = Field(min_length=1, max_length=40)
    origin: Literal["source_extract", "manual_transcription", "generated"] = "source_extract"

    @model_validator(mode="after")
    def valid_relationship(self):
        if self.source.namespace == self.target.namespace and self.source.code == self.target.code:
            raise ValueError("An alias cannot point to itself")
        if self.relationship_type == "generic_obd_equivalent" and self.target.code_type != "generic_standardized":
            raise ValueError("A generic OBD equivalent must target a generic standardized identifier")
        return self


class DiagnosticDatasetImport(Strict):
    schema_version: Literal["1.0"]
    source_id: str = Field(min_length=1)
    namespace: NamespaceInput
    dataset: DatasetInput
    definitions: list[DefinitionInput] = Field(default_factory=list, max_length=5000)
    aliases: list[AliasInput] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def counts_are_coherent(self):
        if self.dataset.documented_available_count < len(self.definitions):
            raise ValueError("documented_available_count cannot be smaller than imported definitions")
        record_ids = [item.provenance.record_id for item in self.definitions]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("Definition provenance record_id values must be unique within a dataset")
        aliases = [
            (item.source.namespace, item.source.code, item.target.namespace, item.target.code, item.relationship_type)
            for item in self.aliases
        ]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Diagnostic aliases must be unique within a dataset")
        return self


class VehicleDiagnosticContext(Strict):
    manufacturer: str | None = None
    brand: str | None = None
    vehicle_platform: str | None = None
    model: str | None = None
    model_year: int | None = None
    engine_code: str | None = None
    transmission_code: str | None = None
    ecu_module: str | None = None
    ecu_identifiers: list[str] = Field(default_factory=list)


class DiagnosticResolveRequest(Strict):
    namespace: str
    code: str
    vehicle_id: str | None = None
    ecu_module: str | None = Field(default=None, max_length=120)
    ecu_identifiers: list[str] = Field(default_factory=list, max_length=50)
    failure_type: str | None = Field(default=None, pattern=r"^[0-9A-F]{2}$")
    status_byte: int | None = Field(default=None, ge=0, le=255)

    @model_validator(mode="before")
    @classmethod
    def separate_uds_observation(cls, value):
        value = dict(value)
        parsed = split_uds_display(value.get("code", ""))
        value["code"] = parsed.pop("code")
        for key, item in parsed.items():
            if item is not None:
                if value.get(key) not in (None, item):
                    raise ValueError(f"Conflicting {key}")
                value[key] = item
        return value

    @field_validator("namespace")
    @classmethod
    def valid_namespace(cls, value):
        return normalize_namespace(value)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value):
        return normalize_identifier(value)


class PromotionInput(Strict):
    target_stage: PromotionStage
    reason: str = Field(min_length=10, max_length=500)
