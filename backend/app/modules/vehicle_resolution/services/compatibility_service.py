import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database.models import DiagnosticTroubleCode,EcuConfiguration,KnowledgeItem,KnowledgeSource,VehicleConfiguration
from app.modules.dtc.service import resolve_dtc,source_reference

def _scope_matches(scope:dict,config:VehicleConfiguration,ecus:list[EcuConfiguration]):
    values={"make":config.make,"model":config.model,"generation":config.generation,"model_year":config.model_year,"market":config.market,"engine_code":config.engine_code,"transmission_code":config.transmission_code,"type_variant_version":config.type_variant_version}
    matched=[]
    for key,expected in scope.items():
        if key=="year_from":
            if not config.model_year or config.model_year<int(expected):return False,[]
        elif key=="year_to":
            if not config.model_year or config.model_year>int(expected):return False,[]
        elif key in {"ecu_part_number","calibration_id","software_version","ecu_family"}:
            attr={"ecu_part_number":"part_number","software_version":"software_number","ecu_family":"ecu_type"}.get(key,key)
            actuals=[getattr(e,attr) for e in ecus]
            if expected not in actuals:return False,[]
        elif str(values.get(key)) != str(expected): return False,[]
        matched.append(key)
    return True,matched

def compatibility(db:Session,config:VehicleConfiguration,codes:list[str]):
    ecus=db.scalars(select(EcuConfiguration).where(EcuConfiguration.vehicle_configuration_id==config.id)).all()
    definitions=[]; unavailable=[]; packs=[]; warnings=[]
    for raw_code in codes:
        code=raw_code.upper();resolved=resolve_dtc(db,code,{"vehicle_id":config.vehicle_id});dtc=db.scalar(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.code==code))
        if not resolved:
            warnings.append(f"{code} est invalide.")
            continue
        if resolved.documented:
            definitions.append({"code":code,"title":resolved.description,"specificity":resolved.definition_type,"source":resolved.source,"matched_fields":[]})
        else:
            unavailable.append(resolved.as_dict());warnings.append(f"{code}: {resolved.description}")
        if not dtc:continue
        for item in db.scalars(select(KnowledgeItem).where(KnowledgeItem.dtc_id==dtc.id)).all():
            scope=(item.structured_data or {}).get("compatibility_scope",{})
            if item.vehicle_profile_id and item.vehicle_profile_id != config.vehicle_id and not scope: continue
            ok,matched=_scope_matches(scope,config,ecus)
            source=db.get(KnowledgeSource,item.source_id)
            if not ok or not item.human_verified or not source or source.review_status!="reviewed": continue
            specificity="vehicle_profile" if item.vehicle_profile_id else ("ecu_specific" if any(x in matched for x in ("ecu_part_number","calibration_id")) else "configuration_specific" if matched else "generic_knowledge")
            packs.append({"id":item.id,"code":code,"title":item.title,"item_type":item.item_type,"specificity":specificity,"source":source_reference(source,scope),"matched_fields":matched})
    rank={"ecu_specific":0,"vehicle_profile":1,"configuration_specific":2,"generic_knowledge":3}
    packs.sort(key=lambda x:rank[x["specificity"]])
    if config.precision_level in {"unknown","basic_vehicle"}: warnings.append("Configuration peu précise : seuls les contenus génériques sont fiables.")
    return {"vehicle_configuration_id":config.id,"precision_level":config.precision_level,"matched_definitions":definitions,"unavailable_definitions":unavailable,"matched_knowledge_packs":packs,"warnings":warnings}
