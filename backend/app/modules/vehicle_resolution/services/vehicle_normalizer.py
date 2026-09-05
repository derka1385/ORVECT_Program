import re
from datetime import datetime,timezone

BRANDS={"VW":"Volkswagen","VOLKSWAGEN":"Volkswagen","MERCEDES-BENZ":"Mercedes-Benz","MERCEDES":"Mercedes-Benz","PEUGEOT":"Peugeot","CITROEN":"Citroën","RENAULT":"Renault","AUDI":"Audi","BMW":"BMW"}
FUELS={"GAZOLE":"diesel","DIESEL":"diesel","ESSENCE":"gasoline","PETROL":"gasoline","GASOLINE":"gasoline","HYBRIDE":"hybrid","HYBRID":"hybrid","ELECTRIQUE":"electric","ELECTRIC":"electric"}
TRANSMISSIONS={"BVM":"manual","MANUAL":"manual","MANUELLE":"manual","AUTOMATIC":"automatic","AUTOMATIQUE":"automatic","BVA":"automatic","ROBOTIZED":"robotized","ROBOTISEE":"robotized","CVT":"cvt"}

class VehicleNormalizer:
    @staticmethod
    def registration(value:str)->str:return re.sub(r"[^A-Z0-9]","",value.upper())
    @staticmethod
    def vin(value:str)->str:return re.sub(r"\s+","",value.upper())
    @staticmethod
    def text(value):return value.strip() if isinstance(value,str) and value.strip() else None
    def normalize(self,raw:dict,provider:str)->dict:
        source=dict(raw);make=self.text(raw.get("make") or raw.get("brand"));fuel=self.text(raw.get("fuel_type") or raw.get("fuelType") or raw.get("fuel"));transmission=self.text(raw.get("transmission_type") or raw.get("transmissionType"))
        kw=self._number(raw.get("engine_power_kw") or raw.get("powerKw"));hp=self._number(raw.get("engine_power_hp") or raw.get("powerHp"))
        if hp is None and kw is not None:hp=round(kw*1.35962,1)
        if kw is None and hp is not None:kw=round(hp*.735499,1)
        values={
            "make":BRANDS.get((make or "").upper(),make),"model":self.text(raw.get("model")),"generation":self.text(raw.get("generation")),"type_variant_version":self.text(raw.get("type_variant_version") or raw.get("variant") or raw.get("version")),"model_year":self._integer(raw.get("model_year") or raw.get("modelYear") or raw.get("year")),"body_type":self.text(raw.get("body_type") or raw.get("bodyType")),"fuel_type":FUELS.get((fuel or "").upper(),fuel.lower() if fuel else None),"engine_family":self.text(raw.get("engine_family") or raw.get("engineFamily")),"engine_name":self.text(raw.get("engine_name") or raw.get("engineName")),"engine_code":self.text(raw.get("engine_code") or raw.get("engineCode")),"engine_displacement_cc":self._integer(raw.get("engine_displacement_cc") or raw.get("displacementCc")),"engine_power_kw":kw,"engine_power_hp":hp,"engine_torque_nm":self._number(raw.get("engine_torque_nm") or raw.get("torqueNm")),"transmission_code":self.text(raw.get("transmission_code") or raw.get("transmissionCode")),"transmission_type":TRANSMISSIONS.get((transmission or "").upper(),transmission.lower() if transmission else None),"transmission_gears":self._integer(raw.get("transmission_gears") or raw.get("gears")),"drivetrain":self.text(raw.get("drivetrain")),"emission_standard":self.text(raw.get("emission_standard") or raw.get("emissionStandard")),"tecdoc_k_type":self.text(raw.get("tecdoc_k_type") or raw.get("tecdocKType") or raw.get("kType")),"cnit":self.text(raw.get("cnit")),"type_mine":self.text(raw.get("type_mine") or raw.get("typeMine")),"engine_ecu_manufacturer":self.text(raw.get("engine_ecu_manufacturer") or raw.get("engineEcuManufacturer")),"engine_ecu_model":self.text(raw.get("engine_ecu_model") or raw.get("engineEcuModel")),"provider_name":provider,"raw_provider_value":source,"retrieved_at":datetime.now(timezone.utc).isoformat()}
        return {k:v for k,v in values.items() if v is not None}
    @staticmethod
    def _number(value):
        try:return float(value) if value not in (None,"") else None
        except (TypeError,ValueError):return None
    @staticmethod
    def _integer(value):
        try:return int(float(value)) if value not in (None,"") else None
        except (TypeError,ValueError):return None
