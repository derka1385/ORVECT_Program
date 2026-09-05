from collections import defaultdict,deque
from datetime import datetime,timedelta,timezone
from pathlib import Path
from fastapi import APIRouter,Depends,File,Form,HTTPException,Response,UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.auth import active_garage_id,authenticated_user_id
from app.database.models import AICall,DiagnosticEvent,DiagnosticHypothesis,DiagnosticImage,DiagnosticObservation,DiagnosticSession,DiagnosticStep,VehicleConfiguration,VehicleProfile,now
from app.database.session import get_db
from app.modules.diagnostic_data.resolver import DiagnosticDataResolver,build_vehicle_context
from .analysis_service import AnalysisInProgress,analyze_case
from .image_service import InvalidImage,cleanup_expired_images,process_image,safe_unlink
from .providers import AIInvalidResponse,AIProviderUnavailable
from .schemas import DTCPreviewInput,DiagnosticAnalysis,DiagnosticCreate,FaultCodesInput,MeasurementInput,StepResultInput

router=APIRouter(prefix="/api/diagnostics",tags=["diagnostic-ai"]);calls=defaultdict(deque);diagnostic_data_resolver=DiagnosticDataResolver()
def serialize(o):
    hidden={"vin","vin_encrypted","vin_fingerprint","registration_encrypted","registration_fingerprint"} if isinstance(o,VehicleProfile) else set()
    return {c.name:getattr(o,c.name) for c in o.__table__.columns if c.name not in hidden}
def owned_case(db,id,gid):
    row=db.scalar(select(DiagnosticSession).where(DiagnosticSession.id==id,DiagnosticSession.garage_id==gid))
    if not row:raise HTTPException(404,"Dossier diagnostic introuvable")
    return row
def rate_limit(gid):
    current=datetime.now(timezone.utc);q=calls[gid]
    while q and q[0]<current-timedelta(minutes=1):q.popleft()
    if len(q)>=settings.gemini_rate_limit_per_minute:raise HTTPException(429,"Trop d’analyses. Réessayez dans une minute.")
    q.append(current)

@router.post("",status_code=201)
def create_case(data:DiagnosticCreate,db:Session=Depends(get_db),gid:str=Depends(active_garage_id),uid:str=Depends(authenticated_user_id)):
    vehicle=db.scalar(select(VehicleProfile).where(VehicleProfile.id==data.vehicle_id,VehicleProfile.garage_id==gid))
    if not vehicle:raise HTTPException(404,"Véhicule introuvable")
    config=db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id==vehicle.id))
    effective_engine=config.engine_code_confirmed_by_user or config.engine_code if config else vehicle.engine_code
    if not effective_engine or effective_engine=="UNKNOWN" or (config and not config.confirmed_by_user):raise HTTPException(409,"Confirmez une motorisation avant de lancer le diagnostic")
    row=DiagnosticSession(garage_id=gid,technician_id=uid,vehicle_profile_id=data.vehicle_id,status="draft",mileage=data.mileage,customer_complaint=data.symptoms,observed_symptoms=data.symptoms,appearance_circumstances=data.circumstances);db.add(row);db.commit();return serialize(row)

@router.post("/dtc-preview")
def preview_fault_codes(data:DTCPreviewInput,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    vehicle=db.scalar(select(VehicleProfile).where(VehicleProfile.id==data.vehicle_id,VehicleProfile.garage_id==gid))
    if not vehicle:raise HTTPException(404,"Véhicule introuvable")
    items=[]
    for item in data.fault_codes:
        context=build_vehicle_context(db,vehicle,item.ecu,item.ecu_identifiers)
        resolution=diagnostic_data_resolver.resolve(db,item.namespace,item.code,context)
        items.append({
            "namespace":item.namespace,
            "code":resolution["code"],
            "ecu":item.ecu,
            "definition_type":resolution["definition_type"],
            "description":resolution["description"],
            "documented":resolution["documented"],
            "resolution_status":resolution["status"],
            "source":resolution["source"],
            "missing_information":resolution["missing_information"],
            "candidate_count":len(resolution["candidates"]),
            "technician_verification":item.technician_verification,
            "technician_note":item.technician_note,
        })
    return {"items":items,"count":len(items)}
@router.get("/{case_id}")
def detail(case_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    case=owned_case(db,case_id,gid)
    latest=db.scalar(select(AICall).where(AICall.session_id==case.id,AICall.status=="completed").order_by(AICall.created_at.desc()))
    analysis=None
    analysis_status="not_available" if latest is None else "legacy_requires_review"
    if latest and latest.schema_version=="2.0":
        try:
            analysis=DiagnosticAnalysis.model_validate(latest.output_payload).model_dump(mode="json")
            analysis_status="current"
        except ValidationError:
            # Preserve the stored payload; never invent safety/provenance fields
            # to make an old or invalid result appear compatible with this UI.
            pass
    return {"case":serialize(case),"vehicle":serialize(case.vehicle),"observations":[serialize(x) for x in db.scalars(select(DiagnosticObservation).where(DiagnosticObservation.session_id==case.id)).all()],"images":[{**serialize(x),"storage_path":None,"thumbnail_path":None,"url":f"/api/diagnostics/{case.id}/images/{x.id}"} for x in db.scalars(select(DiagnosticImage).where(DiagnosticImage.session_id==case.id)).all()],"steps":[serialize(x) for x in db.scalars(select(DiagnosticStep).where(DiagnosticStep.session_id==case.id).order_by(DiagnosticStep.step_order)).all()],"analysis":analysis,"analysis_status":analysis_status}
@router.delete("/{case_id}",status_code=204)
def delete_case(case_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    case=owned_case(db,case_id,gid)
    for image in db.scalars(select(DiagnosticImage).where(DiagnosticImage.session_id==case.id)).all():
        for candidate in (image.storage_path,image.thumbnail_path):safe_unlink(candidate)
        db.delete(image)
    for model in (AICall,DiagnosticEvent,DiagnosticHypothesis,DiagnosticStep,DiagnosticObservation):
        for row in db.scalars(select(model).where(model.session_id==case.id)).all():db.delete(row)
    db.delete(case);db.commit();return Response(status_code=204)
@router.post("/{case_id}/fault-codes",status_code=201)
def fault_codes(case_id:str,data:FaultCodesInput,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    case=owned_case(db,case_id,gid)
    if case.status=="analyzing":raise HTTPException(409,"Analyse en cours")
    existing=db.scalar(select(func.count()).select_from(DiagnosticObservation).where(DiagnosticObservation.session_id==case.id,DiagnosticObservation.observation_type=="DTC")) or 0
    if existing+len(data.fault_codes)>settings.max_diagnostic_fault_codes:raise HTTPException(413,"Limite de codes défaut atteinte pour ce diagnostic")
    rows=[]
    for item in data.fault_codes:
        context=build_vehicle_context(db,case.vehicle,item.ecu,item.ecu_identifiers)
        resolution=diagnostic_data_resolver.resolve(db,item.namespace,item.code,context)
        row=DiagnosticObservation(session_id=case.id,observation_type="DTC",key=item.code,value={"raw_code":item.code,"normalized_code":item.code,"namespace":item.namespace,"category":resolution["definition_type"],"ecu":item.ecu,"ecu_identifiers":item.ecu_identifiers,"sub_code":None,"status":item.status,"freeze_frame":item.freeze_frame,"resolution_status":resolution["status"],"description":resolution["description"],"description_source_id":resolution["source"]["source_id"] if resolution["source"] else None,"description_source":resolution["source"],"missing_information":resolution["missing_information"],"technician_verification":item.technician_verification,"technician_note":item.technician_note},source="manual_entry");db.add(row);rows.append(row)
    db.commit();return [serialize(x) for x in rows]
@router.post("/{case_id}/measurements",status_code=201)
def measurement(case_id:str,data:MeasurementInput,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    case=owned_case(db,case_id,gid);count=db.scalar(select(func.count()).select_from(DiagnosticObservation).where(DiagnosticObservation.session_id==case.id,DiagnosticObservation.observation_type=="measurement")) or 0
    if count>=settings.max_diagnostic_measurements:raise HTTPException(413,"Limite de mesures atteinte pour ce diagnostic")
    row=DiagnosticObservation(session_id=case.id,observation_type="measurement",key=data.name,value={"value":data.value,"conditions":data.conditions},unit=data.unit,source=data.source);db.add(row);db.commit();return serialize(row)
@router.post("/{case_id}/images",status_code=201)
async def images(case_id:str,files:list[UploadFile]=File(...),category:str=Form("other"),description:str=Form(""),db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    cleanup_expired_images(db);case=owned_case(db,case_id,gid);count=len(db.scalars(select(DiagnosticImage).where(DiagnosticImage.session_id==case.id)).all())
    if case.status=="analyzing":raise HTTPException(409,"Analyse en cours")
    if count+len(files)>settings.max_diagnostic_images:raise HTTPException(413,f"Maximum {settings.max_diagnostic_images} images par dossier")
    blobs=[];total=0
    for file in files:
        raw=await file.read(settings.max_image_bytes+1);total+=len(raw)
        if len(raw)>settings.max_image_bytes or total>settings.max_image_total_bytes:raise HTTPException(413,"Limite de taille des images dépassée")
        blobs.append((file,raw))
    rows=[]
    try:
        for file,raw in blobs:
            row=DiagnosticImage(session_id=case.id,**process_image(raw,file.content_type,category,description));db.add(row);rows.append(row)
        db.commit();return [{**serialize(x),"storage_path":None,"thumbnail_path":None,"url":f"/api/diagnostics/{case.id}/images/{x.id}"} for x in rows]
    except InvalidImage as exc:
        db.rollback()
        for row in rows:
            for candidate in (row.storage_path,row.thumbnail_path):
                Path(candidate).unlink(missing_ok=True)
        raise HTTPException(415,str(exc))
@router.get("/{case_id}/images/{image_id}")
def image_file(case_id:str,image_id:str,thumbnail:bool=True,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    case=owned_case(db,case_id,gid);row=db.scalar(select(DiagnosticImage).where(DiagnosticImage.id==image_id,DiagnosticImage.session_id==case.id))
    if not row:raise HTTPException(404,"Image introuvable")
    path=row.thumbnail_path if thumbnail else row.storage_path
    if not Path(path).exists():raise HTTPException(410,"Image supprimée")
    return FileResponse(path,media_type=row.mime_type,headers={"Cache-Control":"private, max-age=300"})
@router.post("/{case_id}/analyze")
async def analyze(case_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    rate_limit(gid);case=owned_case(db,case_id,gid)
    try:return await analyze_case(db,case,False)
    except AnalysisInProgress as exc:raise HTTPException(409,str(exc))
    except ValueError as exc:raise HTTPException(422,str(exc))
    except AIProviderUnavailable as exc:raise HTTPException(503,str(exc))
    except AIInvalidResponse as exc:raise HTTPException(502,str(exc))
@router.post("/{case_id}/steps/{step_id}/result")
def step_result(case_id:str,step_id:str,data:StepResultInput,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    case=owned_case(db,case_id,gid);step=db.scalar(select(DiagnosticStep).where(DiagnosticStep.id==step_id,DiagnosticStep.session_id==case.id))
    if case.status=="analyzing":raise HTTPException(409,"Analyse en cours")
    if not step:raise HTTPException(404,"Étape introuvable")
    if step.status!="current":raise HTTPException(409,"Seule l’étape courante non terminée peut recevoir un résultat")
    step.status="completed" if data.state in {"positive","negative"} else "blocked";step.result=data.model_dump();step.technician_comment=data.comment;step.completed_at=now();db.commit();return serialize(step)
@router.post("/{case_id}/reanalyze")
async def reanalyze(case_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    rate_limit(gid);case=owned_case(db,case_id,gid)
    try:return await analyze_case(db,case,True)
    except AnalysisInProgress as exc:raise HTTPException(409,str(exc))
    except ValueError as exc:raise HTTPException(422,str(exc))
    except AIProviderUnavailable as exc:raise HTTPException(503,str(exc))
    except AIInvalidResponse as exc:raise HTTPException(502,str(exc))
