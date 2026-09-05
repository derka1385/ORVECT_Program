from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime
from app.database.models import VehicleConfigurationCandidate,VehicleResolutionEvent,VinResolutionRequest,now
from app.database.session import get_db
from app.auth import active_garage_id
from app.modules.vehicle_resolution.schemas import ResolveVin
from app.modules.vehicle_resolution.services.vehicle_resolution_service import resolution_service
from app.modules.vehicle_resolution.services.security import protector
from app.modules.vehicle_resolution.services.vin_validator import VinValidator
from .providers import get_registration_provider
from .schemas import RegistrationLookupInput,VehicleResolveInput,VinLookupInput
from app.modules.vehicle_resolution.services.vehicle_resolver import vehicle_resolver

router=APIRouter(prefix="/api/vehicles",tags=["vehicle-data"]);validator=VinValidator()
def add_event(db,row,kind,payload):db.add(VehicleResolutionEvent(resolution_id=row.id,vehicle_id=row.vehicle_id,event_type=kind,payload=payload,actor_type="system",actor_id=None))
def serialize(o):return {c.name:getattr(o,c.name) for c in o.__table__.columns}
DIRECT_FIELDS={"make","model","generation","type_variant_version","model_year","first_registration_date","body_type","fuel_type","engine_family","engine_code","engine_name","engine_displacement_cc","engine_power_kw","engine_power_hp","engine_torque_nm","transmission_code","transmission_type","transmission_gears","drivetrain","emission_standard","market","tecdoc_k_type","cnit","type_mine","engine_ecu_manufacturer","engine_ecu_model"}

def direct_candidate(db,gid,vin,country,result):
    values={key:value for key,value in (result.get("vehicle") or {}).items() if key in DIRECT_FIELDS and value not in (None,"")}
    if isinstance(values.get("first_registration_date"),str):
        try:values["first_registration_date"]=datetime.fromisoformat(values["first_registration_date"].replace("Z","+00:00"))
        except ValueError:values.pop("first_registration_date",None)
    row=VinResolutionRequest(garage_id=gid,vehicle_id=None,vin_encrypted=protector.encrypt(vin),vin_fingerprint=protector.fingerprint(vin),vin_last_six=vin[-6:],country_code=country,model_year_hint=values.get("model_year"),selected_provider=result["provider"],provider_version=None,provider_request_id=None,status="requires_confirmation",completed_at=now());db.add(row);db.flush()
    critical=("make","model","model_year","engine_code","transmission_type");missing=[key for key in critical if not values.get(key)]
    provenance={key:{"value":value,"origin":"registration_provider","provider":result["provider"],"confidence":.9} for key,value in values.items()}
    candidate=VehicleConfigurationCandidate(resolution_id=row.id,provider_name=result["provider"],confidence_score=max(.25,.9-.1*len(missing)),missing_critical_fields=missing,warnings=["Données fournisseur à confirmer avant diagnostic."],field_provenance=provenance,**values);db.add(candidate);add_event(db,row,"registration_resolved",{"provider":result["provider"],"returned_fields":sorted(values)});db.commit();return row,candidate

@router.post("/resolve")
async def resolve(data:VehicleResolveInput,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    registration_result=None
    if data.registration:
        try:registration_result=await get_registration_provider().lookup_by_registration(data.registration,data.country_code)
        except RuntimeError as exc:raise HTTPException(503,str(exc))
        if not data.vin and not registration_result.get("vin"):return registration_result
    vin=data.vin or registration_result["vin"];validation=validator.validate(vin)
    if not validation.is_valid_format:raise HTTPException(422,{"code":"invalid_vin","errors":validation.errors})
    if registration_result and registration_result.get("vehicle"):
        row,candidate=direct_candidate(db,gid,validation.normalized_vin,data.country_code,registration_result)
        return {"resolution_id":row.id,"vehicle_id":row.vehicle_id,"status":row.status,"masked_vin":"***********"+row.vin_last_six,"registration_status":registration_result["status"],"provider":row.selected_provider,"cache_hit":False,"candidates":[serialize(candidate)],"warnings":[*registration_result.get("warnings",[]),*candidate.warnings]}
    request=ResolveVin(vin=validation.normalized_vin,country_code=data.country_code,model_year_hint=data.model_year_hint,force_refresh=data.force_refresh)
    row,cache_hit=await resolution_service.resolve(db,gid,request,validation,add_event)
    candidates=db.scalars(select(VehicleConfigurationCandidate).where(VehicleConfigurationCandidate.resolution_id==row.id).order_by(VehicleConfigurationCandidate.confidence_score.desc())).all()
    return {"resolution_id":row.id,"vehicle_id":row.vehicle_id,"status":row.status,"masked_vin":"***********"+row.vin_last_six,"registration_status":registration_result["status"] if registration_result else None,"provider":row.selected_provider,"cache_hit":cache_hit,"candidates":[serialize(x) for x in candidates],"warnings":[*(registration_result.get("warnings",[]) if registration_result else []),*[w for x in candidates for w in (x.warnings or [])]]}

@router.post("/resolve-registration")
async def resolve_registration(data:RegistrationLookupInput,gid:str=Depends(active_garage_id)):
    return await vehicle_resolver.resolve_registration(data.registration,data.country_code)

@router.post("/resolve-vin")
async def resolve_vin_normalized(data:VinLookupInput,gid:str=Depends(active_garage_id)):
    validation=validator.validate(data.vin)
    if not validation.is_valid_format:raise HTTPException(422,{"code":"invalid_vin","errors":validation.errors})
    return await vehicle_resolver.resolve_vin(validation.normalized_vin,data.country_code)
