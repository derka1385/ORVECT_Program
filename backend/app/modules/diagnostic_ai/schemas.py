from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceReference(Strict):
    source_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    vehicle_compatibility: dict
    timestamp: str = Field(min_length=1)
    verified: bool


class InterpretedFaultCode(Strict):
    namespace: str = "sae_obd2"
    code: str
    ecu: str | None = None
    meaning: str
    definitionType: Literal["generic_standardized", "manufacturer_specific", "unknown"]
    sourceStatus: Literal["provided_by_database", "ai_general_knowledge_unverified", "not_found"]
    sources: list[SourceReference] = Field(default_factory=list)
    relevance: Literal["primary", "secondary", "consequence", "unknown"]

    @model_validator(mode="after")
    def database_claim_has_source(self):
        if self.sourceStatus == "provided_by_database" and not self.sources:
            raise ValueError("A database-provided DTC definition requires a source")
        if self.sourceStatus != "provided_by_database" and self.sources:
            raise ValueError("Only database-provided definitions may carry database sources")
        return self


class Correlation(Strict):
    relatedCodes: list[str]
    explanation: str
    confidence: float = Field(ge=0, le=1)


class Hypothesis(Strict):
    id: str
    label: str
    component: str | None = None
    confidence: float = Field(ge=0, le=1)
    supportingEvidence: list[str]
    contradictingEvidence: list[str]
    requiredConfirmation: list[str]
    status: Literal["possible", "likely", "unlikely", "rejected"]
    verificationStatus: Literal["verified", "partially_verified", "unverified"]
    sources: list[SourceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def verification_matches_sources(self):
        if not self.sources and self.verificationStatus != "unverified":
            raise ValueError("A source-free hypothesis must be marked unverified")
        return self


class ImageEvidence(Strict):
    imageId: str
    observation: str
    confidence: float = Field(ge=0, le=1)
    limitations: list[str]


class SafetyAssessment(Strict):
    status: Literal["DO_NOT_DRIVE", "STOP_AS_SOON_AS_SAFE", "UNKNOWN"]
    riskLevel: Literal["critical", "high", "unknown"]
    drivingRecommendation: Literal["do_not_drive", "stop_as_soon_as_safe", "unknown"]
    explanation: str
    humanReviewRequired: bool
    ruleIds: list[str]
    decisionSource: Literal["safety_engine"]


class MissingInformation(Strict):
    field: str
    reason: str
    howToObtain: str
    priority: Literal["low", "medium", "high"]


class ExpectedResultAI(Strict):
    outcome: str
    interpretation: str
    nextAction: str


class NextCheck(Strict):
    id: str
    order: int = Field(ge=1)
    title: str
    objective: str
    prerequisites: list[str]
    instructions: list[str]
    safetyWarnings: list[str]
    expectedResults: list[ExpectedResultAI]
    requiredTools: list[str]
    estimatedDifficulty: Literal["easy", "intermediate", "advanced"]
    verificationStatus: Literal["verified", "partially_verified", "unverified"]
    manufacturerProcedure: bool = False
    sources: list[SourceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def procedure_requires_verified_source(self):
        if self.manufacturerProcedure and not any(source.verified for source in self.sources):
            raise ValueError("A manufacturer procedure requires a verified source")
        if not self.sources and self.verificationStatus != "unverified":
            raise ValueError("A source-free check must be marked unverified")
        return self


ConclusionStatus = Literal[
    "insufficient_evidence",
    "vehicle_configuration_not_sufficiently_identified",
    "manufacturer_specific_definition_unavailable",
    "human_escalation_required",
    "testing_required",
    "probable_cause_identified",
]


class FinalConclusion(Strict):
    status: ConclusionStatus
    summary: str


class LLMDiagnosticAnalysis(Strict):
    schemaVersion: Literal["2.0"]
    caseSummary: str
    reasoningApproach: str
    interpretedFaultCodes: list[InterpretedFaultCode] = Field(max_length=30)
    correlations: list[Correlation] = Field(max_length=30)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=20)
    imageEvidence: list[ImageEvidence] = Field(max_length=8)
    missingInformation: list[MissingInformation] = Field(max_length=30)
    nextChecks: list[NextCheck] = Field(max_length=20)
    finalConclusion: FinalConclusion
    warnings: list[str]

    @field_validator("hypotheses")
    @classmethod
    def ranked(cls, value):
        if any(value[i].confidence < value[i + 1].confidence for i in range(len(value) - 1)):
            raise ValueError("Les hypothèses doivent être classées par confiance décroissante")
        return value


class DiagnosticAnalysis(LLMDiagnosticAnalysis):
    safetyAssessment: SafetyAssessment


class DiagnosticCreate(Strict):
    vehicle_id: str
    mileage: int | None = Field(default=None, ge=0)
    symptoms: str = Field(default="", max_length=5000)
    circumstances: str = Field(default="", max_length=3000)


class FaultCodeInput(Strict):
    code: str
    namespace: str | None = None
    ecu: str | None = Field(default=None, max_length=100)
    ecu_identifiers: list[str] = Field(default_factory=list, max_length=50)
    status: Literal["active", "intermittent", "stored", "unknown"] = "unknown"
    freeze_frame: dict = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def normalize(cls, value):
        from app.modules.diagnostic_data.normalization import normalize_identifier

        return normalize_identifier(value)

    @field_validator("namespace")
    @classmethod
    def normalize_namespace_value(cls, value):
        from app.modules.diagnostic_data.normalization import normalize_namespace

        return normalize_namespace(value) if value else value

    @model_validator(mode="after")
    def namespace_is_explicit_for_oem_identifiers(self):
        import re

        if not self.namespace and re.fullmatch(r"[PBCU][0-9A-F]{4}", self.code):
            self.namespace = "sae_obd2"
        if not self.namespace:
            raise ValueError("A diagnostic namespace is required for manufacturer identifiers")
        return self


class FaultCodesInput(Strict):
    fault_codes: list[FaultCodeInput] = Field(min_length=1, max_length=30)


class MeasurementInput(Strict):
    name: str = Field(min_length=1, max_length=100)
    value: float | str | bool
    unit: str | None = Field(default=None, max_length=30)
    conditions: str = Field(default="", max_length=500)
    source: Literal["manual", "obd", "image"] = "manual"


ResultState = Literal["positive", "negative", "inconclusive", "unavailable", "invalid", "refused"]
NON_INFORMATIVE_RESULT_STATES = {"inconclusive", "unavailable", "invalid", "refused"}


class StepResultInput(Strict):
    state: ResultState
    outcome: str = Field(default="", max_length=500)
    measurement: float | None = None
    unit: str | None = Field(default=None, max_length=30)
    comment: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def informative_result_requires_observation(self):
        if self.state in {"positive", "negative"} and not self.outcome.strip():
            raise ValueError("An informative result requires an observed outcome")
        return self
