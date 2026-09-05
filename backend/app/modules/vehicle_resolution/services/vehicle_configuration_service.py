from app.modules.vehicle_resolution.services.precision_service import PrecisionService

EDITABLE_CONFIGURATION_FIELDS={"manufacturer","make","model","generation","model_year","production_date","first_registration_date","market","vehicle_type","body_type","fuel_type","engine_family","engine_name","engine_code","engine_displacement_cc","engine_power_kw","engine_power_hp","engine_torque_nm","engine_induction","transmission_type","transmission_code","transmission_gears","drivetrain","emission_standard","engine_type_approval","equipment","platform","type_variant_version"}

def validated_corrections(values:dict)->dict:
    unknown=set(values)-EDITABLE_CONFIGURATION_FIELDS
    if unknown: raise ValueError(f"Champs non modifiables : {', '.join(sorted(unknown))}")
    return values

def precision_for(values:dict,has_ecu:bool=False,conflict:bool=False):
    return PrecisionService().calculate(values,has_ecu=has_ecu,conflict=conflict)
