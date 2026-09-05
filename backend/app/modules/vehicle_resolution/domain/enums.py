from enum import StrEnum
class ResolutionStatus(StrEnum):
    pending="pending"; validating="validating"; invalid="invalid"; provider_pending="provider_pending"; provider_failed="provider_failed"; candidates_available="candidates_available"; requires_confirmation="requires_confirmation"; confirmed="confirmed"; conflict="conflict"; cancelled="cancelled"
class PrecisionLevel(StrEnum):
    unknown="unknown"; basic_vehicle="basic_vehicle"; model_specific="model_specific"; engine_specific="engine_specific"; variant_specific="variant_specific"; ecu_specific="ecu_specific"; verified_documentation="verified_documentation"
class FieldOrigin(StrEnum):
    provider="provider"; technician_confirmation="technician_confirmation"; ecu_scan="ecu_scan"; imported_report="imported_report"; internal_mapping="internal_mapping"; inferred="inferred"; unknown="unknown"
class CheckDigitStatus(StrEnum):
    valid="valid"; invalid="invalid"; not_applicable="not_applicable"; unknown="unknown"
