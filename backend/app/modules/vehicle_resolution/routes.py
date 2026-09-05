from collections import defaultdict,deque
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.auth import active_garage_id,authenticated_user_id
from app.database.models import EcuConfiguration,VehicleConfiguration,VehicleConfigurationCandidate,VehicleProfile,VehicleResolutionEvent,VinResolutionRequest,now
from app.database.session import get_db
from app.modules.vehicle_resolution.schemas import CompatibilityInput,ConfirmResolution,EcuInput,ResolveVin,ValidateVin,VehicleVerificationInput
from app.modules.vehicle_resolution.services.compatibility_service import compatibility
from app.modules.vehicle_resolution.services.precision_service import PrecisionService
from app.modules.vehicle_resolution.services.security import protector
from app.modules.vehicle_resolution.services.vehicle_resolution_service import resolution_service
from app.modules.vehicle_resolution.services.vin_validator import VinValidator

router=APIRouter(prefix="/api",tags=["vehicle-resolution"]); validator=VinValidator(); precision=PrecisionService(); calls=defaultdict(deque)
CONFIG_FIELDS=("manufacturer","make","model","generation","model_year","production_date","first_registration_date","market","vehicle_type","body_type","fuel_type","engine_family","engine_name","engine_code","engine_displacement_cc","engine_power_kw","engine_power_hp","engine_torque_nm","engine_induction","transmission_type","transmission_code","transmission_gears","drivetrain","emission_standard","engine_type_approval","equipment","platform","type_variant_version","tecdoc_k_type","cnit","type_mine","engine_ecu_manufacturer","engine_ecu_model")

def serialize(obj):
    hidden={"vin","vin_encrypted","vin_fingerprint","registration_encrypted","registration_fingerprint"} if isinstance(obj,VehicleProfile) else set()
    return {c.name:getattr(obj,c.name) for c in obj.__table__.columns if c.name not in hidden}
def event(db,resolution,event_type,payload=None,vehicle_id=None,actor_type="system",actor_id=None):db.add(VehicleResolutionEvent(resolution_id=resolution.id,vehicle_id=vehicle_id,event_type=event_type,payload=payload or {},actor_type=actor_type,actor_id=actor_id))
def owned_resolution(db,rid,gid):
    row=db.scalar(select(VinResolutionRequest).where(VinResolutionRequest.id==rid,VinResolutionRequest.garage_id==gid))
    if not row:raise HTTPException(404,"Résolution VIN introuvable pour ce garage")
    return row
def owned_vehicle(db,vid,gid):
    row=db.scalar(select(VehicleProfile).where(VehicleProfile.id==vid,VehicleProfile.garage_id==gid))
    if not row:raise HTTPException(404,"Véhicule introuvable pour ce garage")
    return row
def candidate_json(c):
    out=serialize(c); out.pop("resolution_id",None); return out
def resolution_json(db,row,cache_hit=False):
    candidates=db.scalars(select(VehicleConfigurationCandidate).where(VehicleConfigurationCandidate.resolution_id==row.id).order_by(VehicleConfigurationCandidate.confidence_score.desc())).all()
    return {"id":row.id,"resolution_id":row.id,"status":row.status,"masked_vin":"***********"+row.vin_last_six,"country_code":row.country_code,"model_year_hint":row.model_year_hint,"provider":row.selected_provider,"provider_version":row.provider_version,"error_code":row.error_code,"error_message":row.error_message_safe,"vehicle_id":row.vehicle_id,"cache_hit":cache_hit,"candidates":[candidate_json(x) for x in candidates],"warnings":[x for c in candidates for x in (c.warnings or [])]}
def rate_limit(gid):
    current=datetime.now(timezone.utc); q=calls[gid]
    while q and q[0]<current-timedelta(minutes=1):q.popleft()
    if len(q)>=settings.vin_rate_limit_per_minute:raise HTTPException(429,"Trop de résolutions VIN. Réessayez dans une minute.")
    q.append(current)

@router.post("/vehicle-resolution/validate-vin")
@router.post("/validate-vin",include_in_schema=False)
def validate_vin(data:ValidateVin,gid:str=Depends(active_garage_id)):return validator.validate(data.vin).model_dump(mode="json")

@router.post("/vehicle-resolution/vin")
async def resolve_vin(data:ResolveVin,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    rate_limit(gid); validation=validator.validate(data.vin)
    if not validation.is_valid_format:raise HTTPException(422,{"code":"invalid_vin","errors":validation.errors})
    if data.vehicle_id:owned_vehicle(db,data.vehicle_id,gid)
    row,cache_hit=await resolution_service.resolve(db,gid,data,validation,event)
    return resolution_json(db,row,cache_hit)

@router.get("/vehicle-resolution/{resolution_id}")
def get_resolution(resolution_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):return resolution_json(db,owned_resolution(db,resolution_id,gid))

@router.post("/vehicle-resolution/{resolution_id}/confirm")
def confirm(resolution_id:str,data:ConfirmResolution,db:Session=Depends(get_db),gid:str=Depends(active_garage_id),uid:str=Depends(authenticated_user_id)):
    row=owned_resolution(db,resolution_id,gid)
    if row.status=="cancelled":raise HTTPException(409,"Cette résolution ne peut plus être confirmée")
    if row.status=="confirmed" and not data.corrections:raise HTTPException(409,"Ce véhicule est déjà confirmé ; fournissez uniquement les corrections techniques vérifiées")
    candidate=None
    if data.candidate_id:
        candidate=db.scalar(select(VehicleConfigurationCandidate).where(VehicleConfigurationCandidate.id==data.candidate_id,VehicleConfigurationCandidate.resolution_id==row.id))
        if not candidate:raise HTTPException(404,"Configuration candidate introuvable")
    if not candidate and not data.corrections and not data.configuration_unknown:raise HTTPException(422,"Sélectionnez une configuration, saisissez manuellement les informations ou indiquez configuration inconnue")
    if set(data.corrections)-set(CONFIG_FIELDS):raise HTTPException(422,"Une correction contient un champ non autorisé")
    values={key:getattr(candidate,key,None) for key in CONFIG_FIELDS}
    values.update(data.corrections)
    if candidate:
        candidate.is_selected=True;candidate.is_confirmed=True;candidate.confirmed_by_user_id=uid;candidate.confirmed_at=now()
        provenance=dict(candidate.field_provenance or {})
        for key,value in data.corrections.items():provenance[key]={"value":value,"origin":"technician_confirmation","provider":None,"confidence":1.0}
        candidate.field_provenance=provenance
    vehicle=owned_vehicle(db,row.vehicle_id,gid) if row.vehicle_id else VehicleProfile(garage_id=gid,make=values.get("make") or "Véhicule",model=values.get("model") or "non identifié",year=values.get("model_year") or datetime.now().year,market=values.get("market") or "unknown",engine_name=values.get("engine_name") or values.get("engine_code") or "Inconnu",engine_code=values.get("engine_code") or "UNKNOWN",fuel_type=values.get("fuel_type") or "unknown",transmission=values.get("transmission_type") or "unknown",vin=None,notes="Créé depuis une résolution VIN ; VIN conservé séparément et chiffré.",is_demo_vehicle=row.selected_provider=="mock")
    if not row.vehicle_id:db.add(vehicle);db.flush();row.vehicle_id=vehicle.id
    if data.registration:
        normalized="".join(ch for ch in data.registration.upper() if ch.isalnum())
        if len(normalized)<4:raise HTTPException(422,"Plaque invalide")
        vehicle.registration_encrypted=protector.encrypt(normalized);vehicle.registration_fingerprint=protector.fingerprint(normalized);vehicle.registration_last_four=normalized[-4:];vehicle.registration_country=(data.registration_country or row.country_code or "FR").upper()
    if values.get("make"):vehicle.make=values["make"]
    if values.get("model"):vehicle.model=values["model"]
    if values.get("model_year"):vehicle.year=values["model_year"]
    if values.get("engine_code"):vehicle.engine_code=values["engine_code"]
    if values.get("engine_name") or values.get("engine_code"):vehicle.engine_name=values.get("engine_name") or values["engine_code"]
    if values.get("fuel_type"):vehicle.fuel_type=values["fuel_type"]
    if values.get("transmission_type"):vehicle.transmission=values["transmission_type"]
    level=precision.calculate(values)
    config=db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id==vehicle.id)) or VehicleConfiguration(vehicle_id=vehicle.id)
    for key,value in values.items():setattr(config,key,value)
    provider_engine=getattr(candidate,"engine_code",None) if candidate else None;manual_engine=data.corrections.get("engine_code")
    config.engine_code_from_provider=provider_engine;config.engine_code_confirmed_by_user=manual_engine if manual_engine and manual_engine!=provider_engine else None;config.providers_used=[candidate.provider_name] if candidate else ["user"];config.field_provenance=(candidate.field_provenance or {}) if candidate else {key:{"value":value,"origin":"user","provider":None,"confidence":1.0} for key,value in values.items() if value not in (None,"")}
    config.selected_candidate_id=candidate.id if candidate else None;config.precision_level=level.value;config.confidence_score=candidate.confidence_score if candidate else .5;config.confirmed_by_user=True;config.confirmed_by_user_id=uid;config.confirmed_at=now();db.add(config)
    row.status="confirmed";row.completed_at=now();event(db,row,"configuration_confirmed",{"candidate_id":candidate.id if candidate else None,"corrected_fields":sorted(data.corrections),"precision_level":level.value,"technician_note":data.technician_note,"configuration_unknown":data.configuration_unknown},vehicle.id,"user",uid)
    db.commit();return {"resolution":resolution_json(db,row),"vehicle":serialize(vehicle),"configuration":serialize(config)}

@router.post("/vehicle-resolution/{resolution_id}/cancel")
def cancel(resolution_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id),uid:str=Depends(authenticated_user_id)):
    row=owned_resolution(db,resolution_id,gid)
    if row.status=="confirmed":raise HTTPException(409,"Une résolution confirmée ne peut pas être annulée")
    row.status="cancelled";row.completed_at=now();event(db,row,"resolution_cancelled",actor_type="user",actor_id=uid);db.commit();return resolution_json(db,row)

@router.post("/vehicle-resolution/{resolution_id}/invalidate-cache")
def invalidate_cache(resolution_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id),uid:str=Depends(authenticated_user_id)):
    row=owned_resolution(db,resolution_id,gid);row.completed_at=datetime(1970,1,1,tzinfo=timezone.utc);event(db,row,"cache_invalidated",actor_type="user",actor_id=uid);db.commit();return {"status":"invalidated","resolution_id":row.id}

@router.post("/vehicle-resolution/{resolution_id}/anonymize")
def anonymize(resolution_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id),uid:str=Depends(authenticated_user_id)):
    row=owned_resolution(db,resolution_id,gid);row.vin_encrypted="";row.vin_fingerprint=f"anonymized:{row.id}";row.vin_last_six="******";event(db,row,"vin_anonymized",actor_type="user",actor_id=uid);db.commit();return {"status":"anonymized","resolution_id":row.id}

@router.post("/vehicles/{vehicle_id}/ecu-configurations",status_code=201)
def add_ecu(vehicle_id:str,data:EcuInput,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    owned_vehicle(db,vehicle_id,gid);config=db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id==vehicle_id))
    if not config:raise HTTPException(409,"Confirmez d’abord la configuration du véhicule")
    payload=data.model_dump(exclude={"reported_engine_code"});ecu=EcuConfiguration(vehicle_configuration_id=config.id,**payload);db.add(ecu)
    conflict=bool(data.reported_engine_code and config.engine_code and data.reported_engine_code!=config.engine_code)
    config.precision_level=precision.calculate(serialize(config),has_ecu=True,conflict=conflict).value
    resolution=db.scalar(select(VinResolutionRequest).where(VinResolutionRequest.vehicle_id==vehicle_id).order_by(VinResolutionRequest.created_at.desc()))
    if resolution:event(db,resolution,"ecu_conflict" if conflict else "ecu_configuration_added",{"ecu_type":data.ecu_type,"conflict":conflict},vehicle_id);resolution.status="conflict" if conflict else resolution.status
    db.commit();return {"ecu_configuration":serialize(ecu),"precision_level":config.precision_level,"conflict":conflict}

@router.post("/vehicles/{vehicle_id}/diagnostic-compatibility")
def check_compatibility(vehicle_id:str,data:CompatibilityInput,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    owned_vehicle(db,vehicle_id,gid);config=db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id==vehicle_id))
    if not config:raise HTTPException(409,"Configuration du véhicule non confirmée")
    result=compatibility(db,config,data.dtcs);result["supported"]=bool(result["matched_definitions"]);result["missing_information"]=[];return result

@router.get("/vehicles/{vehicle_id}/configuration")
def get_vehicle_configuration(vehicle_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    vehicle=owned_vehicle(db,vehicle_id,gid)
    config=db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id==vehicle.id))
    return {
        "vehicle":serialize(vehicle),
        "configuration":serialize(config) if config else None,
        "technical_inspection_history":{
            "status":"provider_not_configured",
            "records":[],
            "message":"No technical-inspection data source is configured.",
        },
    }

@router.put("/vehicles/{vehicle_id}/configuration")
def verify_vehicle_configuration(vehicle_id:str,data:VehicleVerificationInput,db:Session=Depends(get_db),gid:str=Depends(active_garage_id),uid:str=Depends(authenticated_user_id)):
    vehicle=owned_vehicle(db,vehicle_id,gid)
    config=db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id==vehicle.id)) or VehicleConfiguration(vehicle_id=vehicle.id)
    payload=data.model_dump(exclude={"technician_note"})
    payload["platform"]=payload.pop("vehicle_platform")
    for key,value in payload.items():
        if value is not None:setattr(config,key,value)
    provenance=dict(config.field_provenance or {})
    for key,value in payload.items():
        if value is not None:provenance[key]={"value":value,"origin":"technician_verification","provider":None,"confidence":1.0}
    config.field_provenance=provenance
    config.confirmed_by_user=True;config.confirmed_by_user_id=uid;config.confirmed_at=now()
    config.precision_level=precision.calculate(serialize(config)).value
    config.confidence_score=max(config.confidence_score or 0,1.0)
    vehicle.make=data.make;vehicle.model=data.model;vehicle.year=data.model_year;vehicle.engine_code=data.engine_code
    vehicle.engine_name=data.engine_name or data.engine_code
    if data.fuel_type:vehicle.fuel_type=data.fuel_type
    if data.transmission_type:vehicle.transmission=data.transmission_type
    if data.technician_note:vehicle.notes=data.technician_note
    db.add(config);db.commit()
    return {
        "vehicle":serialize(vehicle),
        "configuration":serialize(config),
        "technical_inspection_history":{
            "status":"provider_not_configured",
            "records":[],
            "message":"No technical-inspection data source is configured.",
        },
    }
