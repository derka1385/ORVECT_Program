import re
from pydantic import BaseModel,ConfigDict,Field,model_validator
class VehicleResolveInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    vin:str|None=Field(default=None,max_length=32); registration:str|None=Field(default=None,max_length=20); country_code:str="FR"; model_year_hint:int|None=Field(default=None,ge=1886,le=2100); force_refresh:bool=False
    @model_validator(mode="after")
    def one_identifier(self):
        if not self.vin and not self.registration:raise ValueError("Saisissez une plaque ou un VIN")
        if self.registration:
            value=re.sub(r"[\s-]","",self.registration).upper()
            if not re.fullmatch(r"[A-Z0-9]{4,12}",value):raise ValueError("Plaque invalide")
            self.registration=value
        self.country_code=self.country_code.upper()
        return self

class RegistrationLookupInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    registration:str=Field(min_length=4,max_length=20);country_code:str=Field(default="FR",min_length=2,max_length=2)
    @model_validator(mode="after")
    def normalize(self):
        self.registration=re.sub(r"[^A-Za-z0-9]","",self.registration).upper()
        if not re.fullmatch(r"[A-Z0-9]{4,12}",self.registration):raise ValueError("Plaque invalide")
        self.country_code=self.country_code.upper();return self
class VinLookupInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    vin:str=Field(min_length=11,max_length=32);country_code:str|None=Field(default=None,min_length=2,max_length=2)
