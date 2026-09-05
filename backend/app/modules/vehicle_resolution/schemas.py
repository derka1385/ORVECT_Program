from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Strict(BaseModel): model_config=ConfigDict(extra="forbid")
class ValidateVin(Strict): vin:str
class ResolveVin(Strict):
    vin:str; country_code:str|None=None; model_year_hint:int|None=Field(default=None,ge=1886,le=2100); vehicle_id:str|None=None; provider:str|None=None; force_refresh:bool=False
    @field_validator("country_code")
    @classmethod
    def country(cls,v): return v.upper() if v else v
class ConfirmResolution(Strict):
    candidate_id:str|None=None; corrections:dict[str,Any]=Field(default_factory=dict); technician_note:str|None=Field(default=None,max_length=1000); configuration_unknown:bool=False; registration:str|None=Field(default=None,max_length=20); registration_country:str|None=Field(default=None,min_length=2,max_length=2)
class EcuInput(Strict):
    ecu_type:str; ecu_address:str|None=None; ecu_manufacturer:str|None=None; part_number:str|None=None; hardware_number:str|None=None; software_number:str|None=None; calibration_id:str|None=None; protocol:str|None=None; source:str="ecu_scan"; confidence_score:float=Field(default=.9,ge=0,le=1); reported_engine_code:str|None=None
class CompatibilityInput(Strict):
    dtcs:list[str]=Field(min_length=1,max_length=50); system:str|None=None

class VehicleVerificationInput(Strict):
    make:str=Field(min_length=1,max_length=100)
    model:str=Field(min_length=1,max_length=100)
    model_year:int=Field(ge=1886,le=2100)
    engine_code:str=Field(min_length=1,max_length=100)
    engine_name:str|None=Field(default=None,max_length=150)
    engine_family:str|None=Field(default=None,max_length=100)
    fuel_type:str|None=Field(default=None,max_length=60)
    transmission_type:str|None=Field(default=None,max_length=80)
    transmission_code:str|None=Field(default=None,max_length=100)
    generation:str|None=Field(default=None,max_length=100)
    vehicle_platform:str|None=Field(default=None,max_length=100)
    type_variant_version:str|None=Field(default=None,max_length=150)
    drivetrain:str|None=Field(default=None,max_length=80)
    emission_standard:str|None=Field(default=None,max_length=80)
    engine_ecu_manufacturer:str|None=Field(default=None,max_length=120)
    engine_ecu_model:str|None=Field(default=None,max_length=120)
    technician_note:str|None=Field(default=None,max_length=1000)
