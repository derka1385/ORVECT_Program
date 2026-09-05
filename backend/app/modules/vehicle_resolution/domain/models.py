from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from .enums import CheckDigitStatus
class StrictModel(BaseModel): model_config=ConfigDict(extra="forbid")
class VinValidationResult(StrictModel):
    normalized_vin:str; is_valid_format:bool; is_complete:bool; check_digit_status:CheckDigitStatus; warnings:list[str]=[]; errors:list[str]=[]
class VinProviderResult(StrictModel):
    provider_name:str; provider_version:str; provider_request_id:str|None=None; status:str; raw_vehicle_candidates:list[dict[str,Any]]=[]; warnings:list[str]=[]; requested_at:datetime; completed_at:datetime
class FieldProvenance(StrictModel):
    value:Any=None; origin:str; provider:str|None=None; confidence:float=Field(ge=0,le=1)
class CanonicalCandidate(StrictModel):
    manufacturer:str|None=None; make:str|None=None; model:str|None=None; generation:str|None=None; model_year:int|None=None; production_date:datetime|None=None; first_registration_date:datetime|None=None; market:str|None=None; vehicle_type:str|None=None; body_type:str|None=None; fuel_type:str|None=None; engine_family:str|None=None; engine_name:str|None=None; engine_code:str|None=None; engine_displacement_cc:int|None=None; engine_power_kw:float|None=None; engine_power_hp:float|None=None; engine_torque_nm:float|None=None; engine_induction:str|None=None; engine_cylinders:int|None=None; transmission_type:str|None=None; transmission_code:str|None=None; transmission_gears:int|None=None; drivetrain:str|None=None; emission_standard:str|None=None; engine_type_approval:str|None=None; equipment:list[str]=[]; platform:str|None=None; type_variant_version:str|None=None; provider_name:str; provider_vehicle_id:str|None=None; provider_type_id:str|None=None; confidence_score:float=0; missing_critical_fields:list[str]=[]; warnings:list[str]=[]; field_provenance:dict[str,FieldProvenance]={}

VehicleFieldConfidence=Literal["confirmed","provider_confirmed","user_confirmed","inferred","ambiguous","unknown"]
class VehicleAlternative(StrictModel):
    id:str; label:str; engine_code:str|None=None; engine_name:str|None=None; power_hp:float|None=None; transmission_code:str|None=None; transmission_type:str|None=None; production_period:str|None=None; confidence:float=Field(ge=0,le=1); distinguishing_questions:list[str]=[]
class NormalizedVehicle(StrictModel):
    identification:dict[str,Any]={}; vehicle:dict[str,Any]; engine:dict[str,Any]={}; transmission:dict[str,Any]={}; electronics:dict[str,Any]={}; technical_identifiers:dict[str,Any]={}; metadata:dict[str,Any]; field_confidence:dict[str,VehicleFieldConfidence]={}; field_sources:list[dict[str,Any]]=[]; alternatives:list[VehicleAlternative]=[]
