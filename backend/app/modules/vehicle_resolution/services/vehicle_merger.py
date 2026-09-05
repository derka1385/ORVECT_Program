from collections import defaultdict

IDENTITY_FIELDS=("make","model","generation","type_variant_version","model_year","body_type")
ENGINE_FIELDS=("fuel_type","engine_family","engine_name","engine_code","engine_displacement_cc","engine_power_kw","engine_power_hp","engine_torque_nm","emission_standard")
TRANSMISSION_FIELDS=("transmission_code","transmission_type","transmission_gears","drivetrain")
TECHNICAL_FIELDS=("tecdoc_k_type","cnit","type_mine","engine_ecu_manufacturer","engine_ecu_model")
ALL_FIELDS=IDENTITY_FIELDS+ENGINE_FIELDS+TRANSMISSION_FIELDS+TECHNICAL_FIELDS

class VehicleMerger:
    def merge(self,rows:list[dict])->tuple[dict,list[dict],list[str]]:
        merged={};sources=[];contradictions=[];values=defaultdict(list)
        for row in rows:
            for field in ALL_FIELDS:
                if row.get(field) not in (None,""):values[field].append((row[field],row["provider_name"],float(row.get("provider_confidence",.85))))
        for field,items in values.items():
            unique={str(value).casefold() for value,_,_ in items}
            for value,provider,confidence in items:sources.append({"field":field,"value":value,"provider":provider,"confidence":confidence,"retrievedAt":next((r.get("retrieved_at") for r in rows if r["provider_name"]==provider),None)})
            if len(unique)>1 and field in {"engine_code","engine_power_hp","transmission_code","transmission_type"}:
                contradictions.append(field);continue
            merged[field]=max(items,key=lambda item:item[2])[0]
        return merged,sources,contradictions
