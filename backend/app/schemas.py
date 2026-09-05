from datetime import datetime
import re
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

class StrictModel(BaseModel): model_config = ConfigDict(extra="forbid")
class ORMModel(BaseModel): model_config = ConfigDict(from_attributes=True)

class VehicleCreate(StrictModel):
    make: str; model: str; year: int = Field(ge=1886, le=2100); market: str="generic_demo"; engine_name: str; engine_code: str; fuel_type: str="gasoline"; transmission: str="manual"; vin: str|None=Field(default=None,max_length=17); ecu_reference: str|None=None; notes: str=""; is_demo_vehicle: bool=False
class VehicleOut(VehicleCreate, ORMModel): id: str; garage_id: str; created_at: datetime; updated_at: datetime
class DTCOut(ORMModel): id: str; code: str; category: str; generic_description: str; manufacturer_specific: bool; affected_system: str; severity_hint: str; source_id: str|None
class DTCLookup(StrictModel): vehicle_id: str; codes: list[str] = Field(min_length=1, max_length=20)
class SessionCreate(StrictModel): vehicle_profile_id: str; technician_id: str|None=None; mileage: int|None=Field(default=None, ge=0); customer_complaint: str=""; observed_symptoms: str=""
class ObservationCreate(StrictModel): observation_type: str; key: str; value: dict[str, Any]; unit: str|None=None; source: str="technician"; observed_at: datetime|None=None
class StepComplete(StrictModel):
    state: Literal["positive","negative","inconclusive","unavailable","invalid","refused"]
    result_id: str|None=None; measurement: float|None=None; unit: str|None=None; comment: str|None=None
    @model_validator(mode="after")
    def informative_has_result(self):
        if self.state in {"positive","negative"} and not self.result_id:raise ValueError("Un résultat positif ou négatif exige result_id")
        return self

class OBDDTC(StrictModel):
    code: str; status: Literal["pending","confirmed","permanent","historic"]
    @field_validator("code")
    @classmethod
    def valid_code(cls,v):
        v=v.upper().strip()
        if not re.fullmatch(r"[PBCU][0-9A-F]{4}",v): raise ValueError("code DTC attendu, par exemple P0301, P001A ou P1351")
        return v
class OBDVehicle(StrictModel): vin: str|None=None; make: str; model: str; year: int; engine_code: str
class LiveDatum(StrictModel): key: str; value: float|str|bool; unit: str|None=None
class OBDScan(StrictModel): timestamp: datetime; tool: str; dtcs: list[OBDDTC]=Field(min_length=1,max_length=30); freeze_frame: dict[str,float|int|str|bool]={}; live_data: list[LiveDatum]=Field(default_factory=list,max_length=100)
class OBDReport(StrictModel): schema_version: Literal["1.0"]; vehicle: OBDVehicle; scan: OBDScan

class KnowledgeImportSource(StrictModel):
    title: str; source_type: str; license_type: str; trust_level: str; review_status: Literal["unreviewed","reviewed","rejected","outdated"]; version: str; demo_only: bool
class KnowledgeVehicleScope(StrictModel):
    make: str; model: str; year_from: int; year_to: int; engine_code: str; demo_only: bool
class KnowledgeImportDTC(StrictModel):
    code: str; system: str; possible_causes: list[Any]=Field(max_length=100); test_procedures: list[Any]=Field(max_length=100); demo_only: bool
class KnowledgeImportPayload(StrictModel):
    schema_version: Literal["1.0"]; source: KnowledgeImportSource; vehicle_scope: KnowledgeVehicleScope; dtcs: list[KnowledgeImportDTC]=Field(min_length=1,max_length=100)

class EvidenceSystem(StrictModel): name: str; reason: str
class AIHypothesis(StrictModel): hypothesis_id: str; title: str; suspected_component: str; ranking_score: float=Field(ge=0,le=100); confidence_label: Literal["low","medium","high"]; supporting_evidence: list[str]; contradicting_evidence: list[str]; source_ids: list[str]; source_references:list[dict]=Field(default_factory=list); verification_status:Literal["verified","partially_verified","unverified"]="unverified"
class ExpectedResult(StrictModel): result_id: str; label: str; meaning: str; next_action: str
class AIStep(StrictModel): title: str; objective: str; instructions: list[str]; required_tools: list[str]; expected_results: list[ExpectedResult]; safety_notes: list[str]; source_ids: list[str]; source_references:list[dict]=Field(default_factory=list); verification_status:Literal["verified","partially_verified","unverified"]="unverified"
class AIAnalysisOutput(StrictModel): summary: str; affected_systems: list[EvidenceSystem]; hypotheses: list[AIHypothesis]=Field(default_factory=list); recommended_next_step: AIStep|None=None; conclusion_status:Literal["insufficient_evidence","vehicle_configuration_not_sufficiently_identified","manufacturer_specific_definition_unavailable","human_escalation_required","testing_required"]="testing_required"; limitations: list[str]
