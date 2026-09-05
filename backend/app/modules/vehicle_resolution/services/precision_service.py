from ..domain.enums import PrecisionLevel
class PrecisionService:
    def calculate(self,data:dict,has_ecu=False,has_verified_docs=False,conflict=False)->PrecisionLevel:
        if conflict:return PrecisionLevel.unknown
        if has_verified_docs and has_ecu:return PrecisionLevel.verified_documentation
        if has_ecu:return PrecisionLevel.ecu_specific
        if all(data.get(k) for k in ("make","model","model_year","market","engine_code","transmission_type")) and (data.get("type_variant_version") or data.get("production_date")): return PrecisionLevel.variant_specific
        if all(data.get(k) for k in ("make","model","model_year","market","engine_code")): return PrecisionLevel.engine_specific
        if all(data.get(k) for k in ("make","model","model_year","market")): return PrecisionLevel.model_specific
        if data.get("make") and data.get("model"): return PrecisionLevel.basic_vehicle
        return PrecisionLevel.unknown
