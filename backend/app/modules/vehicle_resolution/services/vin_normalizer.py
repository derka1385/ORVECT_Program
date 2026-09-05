from app.modules.vehicle_resolution.domain.models import CanonicalCandidate, FieldProvenance, VinProviderResult

FIELDS=("manufacturer","make","model","generation","model_year","production_date","first_registration_date","market","vehicle_type","body_type","fuel_type","engine_family","engine_name","engine_code","engine_displacement_cc","engine_power_kw","engine_power_hp","engine_torque_nm","engine_induction","engine_cylinders","transmission_type","transmission_code","transmission_gears","drivetrain","emission_standard","engine_type_approval","equipment","platform","type_variant_version")
CRITICAL=("make","model","model_year","market","engine_code","transmission_type")

def _clean(value):
    if value in (None,"","0","Not Applicable","Not Available"): return None
    return value.strip() if isinstance(value,str) else value

class VinNormalizer:
    def normalize(self,result:VinProviderResult)->list[CanonicalCandidate]:
        candidates=[]
        for raw in result.raw_vehicle_candidates:
            if result.provider_name == "nhtsa_vpic":
                displacement=_clean(raw.get("DisplacementCC"))
                if not displacement and _clean(raw.get("DisplacementL")):
                    try: displacement=round(float(raw["DisplacementL"])*1000)
                    except ValueError: displacement=None
                hp=_clean(raw.get("EngineHP"))
                try:kw=round(float(hp)*.7457,1) if hp else None
                except (TypeError,ValueError):kw=None
                mapped={"manufacturer":raw.get("Manufacturer"),"make":raw.get("Make"),"model":raw.get("Model"),"model_year":raw.get("ModelYear"),"vehicle_type":raw.get("VehicleType"),"body_type":raw.get("BodyClass"),"fuel_type":raw.get("FuelTypePrimary"),"engine_name":raw.get("EngineModel"),"engine_displacement_cc":displacement,"engine_power_hp":hp,"engine_power_kw":kw,"engine_cylinders":raw.get("EngineCylinders"),"transmission_type":raw.get("TransmissionStyle"),"transmission_gears":raw.get("TransmissionSpeeds"),"drivetrain":raw.get("DriveType"),"engine_induction":raw.get("Turbo"),"type_variant_version":raw.get("Series") or raw.get("Trim"),"provider_vehicle_id":raw.get("VehicleDescriptor")}
                confidence=.76
                warnings=["La couverture vPIC est principalement nord-américaine ; confirmez les données pour un véhicule européen."]
            else:
                mapped={k:v for k,v in raw.items() if not k.startswith("_")}; confidence=float(raw.get("_confidence",.7)); warnings=[]
            for key in list(mapped): mapped[key]=_clean(mapped[key])
            for key in ("model_year","engine_displacement_cc","engine_cylinders","transmission_gears"):
                if mapped.get(key):
                    try: mapped[key]=int(float(mapped[key]))
                    except (TypeError,ValueError): mapped[key]=None
            for key in ("engine_power_kw","engine_power_hp","engine_torque_nm"):
                if mapped.get(key):
                    try:mapped[key]=float(mapped[key])
                    except (TypeError,ValueError):mapped[key]=None
            provenance={key:FieldProvenance(value=mapped.get(key),origin="provider",provider=result.provider_name,confidence=confidence) for key in FIELDS if mapped.get(key) is not None}
            missing=[key for key in CRITICAL if not mapped.get(key)]
            candidates.append(CanonicalCandidate(**mapped,provider_name=result.provider_name,confidence_score=max(0,min(1,confidence)),missing_critical_fields=missing,warnings=warnings,field_provenance=provenance))
        return candidates
