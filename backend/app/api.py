import csv, hashlib, io, json, re
from datetime import datetime
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.auth import AuthContext, active_garage_id, authenticated_user_id, require_admin
from app.database.models import AICall, DiagnosticEvent, DiagnosticHypothesis, DiagnosticObservation, DiagnosticSession, DiagnosticStep, DiagnosticTroubleCode, KnowledgeItem, KnowledgeSource, VehicleProfile, now
from app.database.session import get_db
from app.modules.diagnostics.engine import analyze, complete_step, event
from app.modules.dtc.service import resolve_dtc,source_reference
from app.modules.vehicle_resolution.services.deletion_service import delete_vehicle_and_associated_data
from app.modules.vehicle_resolution.services.security import protector
from app.modules.vehicle_resolution.services.vin_validator import VinValidator
from app.schemas import DTCLookup, KnowledgeImportPayload, OBDReport, ObservationCreate, SessionCreate, StepComplete, VehicleCreate

router=APIRouter(prefix="/api")
vin_validator=VinValidator()
def owned_session(db,id,gid):
    obj=db.scalar(select(DiagnosticSession).where(DiagnosticSession.id==id,DiagnosticSession.garage_id==gid))
    if not obj: raise HTTPException(404,"Session introuvable pour ce garage")
    return obj
def serialize(o):
    hidden={"vin","vin_encrypted","vin_fingerprint","registration_encrypted","registration_fingerprint"} if isinstance(o,VehicleProfile) else set()
    return {c.name:getattr(o,c.name) for c in o.__table__.columns if c.name not in hidden}
def paginated(db,query,page,page_size,serializer=None):
    total=db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows=db.scalars(query.offset((page-1)*page_size).limit(page_size)).all()
    render=serializer or serialize
    return {"items":[render(row) for row in rows],"page":page,"page_size":page_size,"total":total}

def knowledge_item_payload(db,row):
    source=db.get(KnowledgeSource,row.source_id)
    if not source:raise HTTPException(500,"Source de connaissance introuvable")
    compatibility=(row.structured_data or {}).get("compatibility_scope") or {"scope":"unspecified"}
    return {**serialize(row),"source":source_reference(source,compatibility)}

@router.get("/health")
def health(db:Session=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status":"ok","service":"diagpilot-api","llm_provider":settings.llm_provider}

@router.get("/public/metrics")
def public_metrics(response:Response,db:Session=Depends(get_db)):
    completed_filter=(AICall.status=="completed",AICall.output_payload.is_not(None))
    diagnostics_analyzed=db.scalar(
        select(func.count(func.distinct(AICall.session_id))).where(*completed_filter)
    ) or 0
    response.headers["Cache-Control"]="public, max-age=15, stale-while-revalidate=60"
    return {
        "diagnostics_analyzed":diagnostics_analyzed,
        "counting_rule":"one_per_diagnostic_after_first_successful_analysis",
    }
@router.get("/vehicles")
def vehicles(page:int=Query(1,ge=1),page_size:int=Query(settings.default_page_size,ge=1,le=settings.max_page_size),db:Session=Depends(get_db),gid:str=Depends(active_garage_id)): return paginated(db,select(VehicleProfile).where(VehicleProfile.garage_id==gid).order_by(VehicleProfile.created_at.desc()),page,page_size)
@router.post("/vehicles",status_code=201)
def create_vehicle(data:VehicleCreate,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    payload=data.model_dump(exclude={"vin"});v=VehicleProfile(garage_id=gid,vin=None,**payload)
    if data.vin:
        validation=vin_validator.validate(data.vin)
        if not validation.is_valid_format:raise HTTPException(422,{"code":"invalid_vin","errors":validation.errors})
        v.vin_encrypted=protector.encrypt(validation.normalized_vin);v.vin_fingerprint=protector.fingerprint(validation.normalized_vin);v.vin_last_six=validation.normalized_vin[-6:]
    db.add(v); db.commit(); return serialize(v)
@router.get("/vehicles/{vehicle_id}")
def vehicle(vehicle_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    v=db.scalar(select(VehicleProfile).where(VehicleProfile.id==vehicle_id,VehicleProfile.garage_id==gid))
    if not v: raise HTTPException(404,"Véhicule introuvable")
    return serialize(v)
@router.put("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id:str,data:VehicleCreate,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    v=db.scalar(select(VehicleProfile).where(VehicleProfile.id==vehicle_id,VehicleProfile.garage_id==gid))
    if not v: raise HTTPException(404,"Véhicule introuvable")
    for k,val in data.model_dump(exclude={"vin"}).items(): setattr(v,k,val)
    if data.vin:
        validation=vin_validator.validate(data.vin)
        if not validation.is_valid_format:raise HTTPException(422,{"code":"invalid_vin","errors":validation.errors})
        v.vin=None;v.vin_encrypted=protector.encrypt(validation.normalized_vin);v.vin_fingerprint=protector.fingerprint(validation.normalized_vin);v.vin_last_six=validation.normalized_vin[-6:]
    db.commit(); return serialize(v)

@router.delete("/vehicles/{vehicle_id}",status_code=204)
def delete_vehicle(vehicle_id:str,db:Session=Depends(get_db),auth:AuthContext=Depends(require_admin)):
    v=db.scalar(select(VehicleProfile).where(VehicleProfile.id==vehicle_id,VehicleProfile.garage_id==auth.garage_id))
    if not v:raise HTTPException(404,"Véhicule introuvable")
    delete_vehicle_and_associated_data(db,v)
    return None

@router.get("/dtcs")
def dtcs(page:int=Query(1,ge=1),page_size:int=Query(settings.default_page_size,ge=1,le=settings.max_page_size),db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    def render(row):
        definition=resolve_dtc(db,row.code)
        return {**serialize(row),**definition.as_dict()}
    return paginated(db,select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.definition_type=="generic_standardized",DiagnosticTroubleCode.confidence_tier.in_(["generic_standard","demo_verified"])).order_by(DiagnosticTroubleCode.code),page,page_size,render)
@router.get("/dtcs/{code}")
def dtc(code:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    definition=resolve_dtc(db,code)
    if definition:return definition.as_dict()
    raise HTTPException(404,"Code DTC syntaxiquement invalide")
@router.post("/dtcs/lookup")
def lookup(data:DTCLookup,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    if not db.scalar(select(VehicleProfile).where(VehicleProfile.id==data.vehicle_id,VehicleProfile.garage_id==gid)): raise HTTPException(404,"Véhicule introuvable")
    codes=list(dict.fromkeys(x.upper() for x in data.codes))
    resolved=[resolve_dtc(db,code,{"vehicle_id":data.vehicle_id}) for code in codes]
    invalid=sorted(code for code,item in zip(codes,resolved) if item is None)
    valid=[item.as_dict() for item in resolved if item]
    supported=[item for item in valid if item["documented"]]
    unavailable=[item for item in valid if not item["documented"]]
    return {"supported":supported,"unavailable":unavailable,"invalid":invalid,"unsupported":sorted([item["code"] for item in unavailable]+invalid)}

@router.post("/diagnostic-sessions",status_code=201)
def create_session(data:SessionCreate,db:Session=Depends(get_db),gid:str=Depends(active_garage_id),uid:str=Depends(authenticated_user_id)):
    if not db.scalar(select(VehicleProfile).where(VehicleProfile.id==data.vehicle_profile_id,VehicleProfile.garage_id==gid)): raise HTTPException(404,"Véhicule introuvable pour ce garage")
    s=DiagnosticSession(garage_id=gid,technician_id=uid,**data.model_dump(exclude={"technician_id"})); db.add(s); db.flush(); event(db,s.id,"session_created",{"vehicle_profile_id":s.vehicle_profile_id},s.technician_id); db.commit(); return serialize(s)
@router.get("/diagnostic-sessions")
def sessions(page:int=Query(1,ge=1),page_size:int=Query(settings.default_page_size,ge=1,le=settings.max_page_size),db:Session=Depends(get_db),gid:str=Depends(active_garage_id)): return paginated(db,select(DiagnosticSession).where(DiagnosticSession.garage_id==gid).order_by(DiagnosticSession.created_at.desc()),page,page_size)
@router.get("/diagnostic-sessions/{session_id}")
def session_detail(session_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    s=owned_session(db,session_id,gid); out=serialize(s); out["vehicle"]=serialize(s.vehicle); out["observations"]=[serialize(x) for x in db.scalars(select(DiagnosticObservation).where(DiagnosticObservation.session_id==s.id)).all()]; return out
@router.post("/diagnostic-sessions/{session_id}/observations",status_code=201)
def add_observation(session_id:str,data:ObservationCreate,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    s=owned_session(db,session_id,gid)
    count=db.scalar(select(func.count()).select_from(DiagnosticObservation).where(DiagnosticObservation.session_id==s.id)) or 0
    if count>=settings.max_diagnostic_observations:raise HTTPException(413,"Limite d’observations atteinte pour ce diagnostic")
    o=DiagnosticObservation(session_id=s.id,**data.model_dump(exclude_none=True)); db.add(o); event(db,s.id,"dtc_added" if data.observation_type=="DTC" else "observation_added",data.model_dump(mode="json"),s.technician_id); db.commit(); return serialize(o)
@router.post("/diagnostic-sessions/{session_id}/analyze")
def run_analysis(session_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    s=owned_session(db,session_id,gid)
    codes=[o.key for o in db.scalars(select(DiagnosticObservation).where(DiagnosticObservation.session_id==s.id,DiagnosticObservation.observation_type=="DTC")).all()]
    if not codes: raise HTTPException(422,"Ajoutez au moins un code DTC avant l’analyse")
    invalid=[code for code in codes if not re.fullmatch(r"[PBCU][0-9A-F]{4}",code.upper())]
    if invalid: raise HTTPException(422,f"Format DTC invalide : {', '.join(invalid)}")
    try: return analyze(db,s)
    except ValueError as e: raise HTTPException(409,str(e))
@router.get("/diagnostic-sessions/{session_id}/hypotheses")
def hypotheses(session_id:str,page:int=Query(1,ge=1),page_size:int=Query(settings.default_page_size,ge=1,le=settings.max_page_size),db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    owned_session(db,session_id,gid); return paginated(db,select(DiagnosticHypothesis).where(DiagnosticHypothesis.session_id==session_id).order_by(DiagnosticHypothesis.probability_score.desc()),page,page_size)
@router.get("/diagnostic-sessions/{session_id}/steps")
def steps(session_id:str,page:int=Query(1,ge=1),page_size:int=Query(settings.default_page_size,ge=1,le=settings.max_page_size),db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    owned_session(db,session_id,gid); return paginated(db,select(DiagnosticStep).where(DiagnosticStep.session_id==session_id).order_by(DiagnosticStep.step_order),page,page_size)
@router.post("/diagnostic-sessions/{session_id}/steps/{step_id}/complete")
def finish_step(session_id:str,step_id:str,data:StepComplete,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    s=owned_session(db,session_id,gid); step=db.scalar(select(DiagnosticStep).where(DiagnosticStep.id==step_id,DiagnosticStep.session_id==s.id,DiagnosticStep.status=="current"))
    if not step: raise HTTPException(409,"Étape courante introuvable ou déjà terminée")
    if data.result_id and data.result_id not in [x["result_id"] for x in step.expected_results]: raise HTTPException(422,"Résultat non prévu pour cette étape")
    expected_state={"fault_moved_to_cylinder_2":"positive","fault_stayed_on_cylinder_1":"negative"}.get(data.result_id)
    if expected_state and data.state!=expected_state:raise HTTPException(422,"L’état du résultat ne correspond pas au résultat sélectionné")
    return serialize(complete_step(db,s,step,data))
@router.post("/diagnostic-sessions/{session_id}/complete")
def finish_session(session_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    s=owned_session(db,session_id,gid); s.status="completed"; s.completed_at=now(); event(db,s.id,"report_generated",{"status":"completed"},s.technician_id); db.commit(); return {"status":"completed","report_url":f"/api/diagnostic-sessions/{s.id}/report"}
@router.get("/diagnostic-sessions/{session_id}/report")
def report(session_id:str,db:Session=Depends(get_db),gid:str=Depends(active_garage_id)):
    s=owned_session(db,session_id,gid); hs=db.scalars(select(DiagnosticHypothesis).where(DiagnosticHypothesis.session_id==s.id).order_by(DiagnosticHypothesis.probability_score.desc())).all(); ss=db.scalars(select(DiagnosticStep).where(DiagnosticStep.session_id==s.id).order_by(DiagnosticStep.step_order)).all(); src={i for h in hs for i in h.source_ids}
    return {"disclaimer":"RAPPORT DE DÉMONSTRATION — ne pas utiliser sur un véhicule réel.","session":serialize(s),"vehicle":serialize(s.vehicle),"dtcs":[o.key for o in db.scalars(select(DiagnosticObservation).where(DiagnosticObservation.session_id==s.id,DiagnosticObservation.observation_type=="DTC")).all()],"tests":[serialize(x) for x in ss],"hypotheses":[serialize(x) for x in hs],"leading_hypothesis":serialize(hs[0]) if hs else None,"sources":[serialize(x) for x in db.scalars(select(KnowledgeSource).where(KnowledgeSource.id.in_(src))).all()] if src else [],"limitations":["Classement interne non scientifique","Corpus fictif","Validation professionnelle requise"]}

@router.get("/knowledge/sources")
def sources(page:int=Query(1,ge=1),page_size:int=Query(settings.default_page_size,ge=1,le=settings.max_page_size),db:Session=Depends(get_db),auth:AuthContext=Depends(require_admin)): return paginated(db,select(KnowledgeSource).order_by(KnowledgeSource.created_at.desc()),page,page_size)
@router.post("/knowledge/sources",status_code=201)
def source(data:dict,db:Session=Depends(get_db),auth:AuthContext=Depends(require_admin)):
    allowed={"title","source_type","publisher","version","license_type","source_url","local_file_path","checksum","trust_level","review_status"}
    if set(data)-allowed: raise HTTPException(422,"Champs de source non autorisés")
    s=KnowledgeSource(**data); db.add(s); db.commit(); return serialize(s)
@router.get("/knowledge/items")
def items(dtc_code:str|None=None,page:int=Query(1,ge=1),page_size:int=Query(settings.default_page_size,ge=1,le=settings.max_page_size),db:Session=Depends(get_db),auth:AuthContext=Depends(require_admin)):
    q=select(KnowledgeItem)
    if dtc_code:
        d=db.scalar(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.code==dtc_code.upper())); q=q.where(KnowledgeItem.dtc_id==d.id) if d else q.where(False)
    return paginated(db,q.order_by(KnowledgeItem.created_at.desc()),page,page_size,lambda row:knowledge_item_payload(db,row))
@router.post("/knowledge/search")
def search_knowledge(data:dict,page:int=Query(1,ge=1),page_size:int=Query(settings.default_page_size,ge=1,le=settings.max_page_size),db:Session=Depends(get_db),auth:AuthContext=Depends(require_admin)):
    term=str(data.get("query","")).strip()[:200];q=select(KnowledgeItem)
    if term:q=q.where((KnowledgeItem.title.ilike(f"%{term}%"))|(KnowledgeItem.content.ilike(f"%{term}%"))|(KnowledgeItem.component.ilike(f"%{term}%")))
    return paginated(db,q.order_by(KnowledgeItem.created_at.desc()),page,page_size,lambda row:knowledge_item_payload(db,row))

def ingest_obd(report:OBDReport,db:Session,gid:str,uid:str,session_id:str|None):
    vehicle=db.scalar(select(VehicleProfile).where(VehicleProfile.garage_id==gid,VehicleProfile.engine_code==report.vehicle.engine_code))
    if not vehicle: raise HTTPException(404,"Aucun véhicule compatible dans ce garage")
    if session_id: s=owned_session(db,session_id,gid)
    else:
        s=DiagnosticSession(garage_id=gid,technician_id=uid,vehicle_profile_id=vehicle.id,status="collecting_data",customer_complaint="Import OBD de démonstration",observed_symptoms=""); db.add(s); db.flush(); event(db,s.id,"session_created",{"origin":"obd_import"},uid)
    supported=[]; unsupported=[]
    for item in report.scan.dtcs:
        definition=resolve_dtc(db,item.code,{"vehicle_id":vehicle.id})
        if definition and definition.documented:supported.append(item.code)
        else:unsupported.append(item.code)
        db.add(DiagnosticObservation(session_id=s.id,observation_type="DTC",key=item.code,value={"status":item.status,"definition_type":definition.definition_type if definition else "unknown","description":definition.description if definition else None,"description_source":definition.source if definition else None},source=f"obd_import:{report.scan.tool}",observed_at=report.scan.timestamp))
    if report.scan.freeze_frame: db.add(DiagnosticObservation(session_id=s.id,observation_type="freeze_frame",key="scan_freeze_frame",value=report.scan.freeze_frame,source=f"obd_import:{report.scan.tool}",observed_at=report.scan.timestamp))
    for item in report.scan.live_data:db.add(DiagnosticObservation(session_id=s.id,observation_type="measurement",key=item.key,value={"value":item.value,"conditions":"imported_live_data"},unit=item.unit,source=f"obd_import:{report.scan.tool}",observed_at=report.scan.timestamp))
    event(db,s.id,"dtc_added",{"supported":supported,"unsupported":unsupported},uid); db.commit(); return {"session_id":s.id,"vehicle_id":vehicle.id,"supported":supported,"unsupported":unsupported,"warnings":["Import de démonstration ; aucune connexion OBD physique."]}

@router.post("/imports/obd-report")
async def import_obd(request:Request,session_id:str|None=None,file:UploadFile|None=File(default=None),db:Session=Depends(get_db),gid:str=Depends(active_garage_id),uid:str=Depends(authenticated_user_id)):
    try:
        if file:
            raw=await file.read(settings.max_upload_bytes+1)
            if len(raw)>settings.max_upload_bytes: raise HTTPException(413,"Fichier supérieur à 1 Mio")
            if file.content_type not in {"application/json","text/json","text/csv","application/csv","application/vnd.ms-excel"}: raise HTTPException(415,"Type de fichier non accepté")
            if "csv" in (file.content_type or ""):
                rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8")))); codes=[{"code":r.get("code",""),"status":r.get("status","confirmed")} for r in rows]
                payload={"schema_version":"1.0","vehicle":{"vin":None,"make":rows[0].get("make","Demo Motors"),"model":rows[0].get("model","DM-1"),"year":int(rows[0].get("year","2020")),"engine_code":rows[0].get("engine_code","DEMO-ENG-01")},"scan":{"timestamp":datetime.now().isoformat(),"tool":"csv-demo-import","dtcs":codes,"freeze_frame":{},"live_data":[]}}
            else: payload=json.loads(raw)
        else: payload=await request.json()
        return ingest_obd(OBDReport.model_validate(payload),db,gid,uid,session_id)
    except (ValidationError,json.JSONDecodeError,UnicodeDecodeError,IndexError,ValueError) as e:
        db.rollback(); raise HTTPException(422,f"Rapport OBD invalide : {e}")

@router.post("/imports/knowledge")
def import_knowledge(data:KnowledgeImportPayload,db:Session=Depends(get_db),auth:AuthContext=Depends(require_admin)):
    canonical=json.dumps(data.model_dump(mode="json"),sort_keys=True,separators=(",",":")); checksum=hashlib.sha256(canonical.encode()).hexdigest()
    duplicate=db.scalar(select(KnowledgeSource).where(KnowledgeSource.checksum==checksum))
    if duplicate: return {"imported":False,"duplicate":True,"source_id":duplicate.id,"checksum":checksum,"items_created":0,"warnings":["Ce contenu exact a déjà été importé."]}
    if not data.source.demo_only or not data.vehicle_scope.demo_only or any(not d.demo_only for d in data.dtcs): raise HTTPException(422,"Le premier import exige demo_only=true à tous les niveaux")
    try:
        src=KnowledgeSource(title=data.source.title,source_type=data.source.source_type,publisher="Import contrôlé DiagPilot",version=data.source.version,license_type=data.source.license_type,trust_level=data.source.trust_level,review_status=data.source.review_status,checksum=checksum); db.add(src); db.flush(); count=0
        for entry in data.dtcs:
            dtc=db.scalar(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.code==entry.code.upper()))
            if not dtc: dtc=DiagnosticTroubleCode(code=entry.code.upper(),category="powertrain",generic_description="",manufacturer_specific=False,affected_system=entry.system,severity_hint="unknown",source_id=None,confidence_tier="unknown",definition_type="unknown"); db.add(dtc); db.flush()
            for typ,rows in (("possible_cause",entry.possible_causes),("test_procedure",entry.test_procedures)):
                for index,row in enumerate(rows):
                    structured=row if isinstance(row,dict) else {"value":row}; title=str(structured.get("title") or structured.get("id") or row)
                    scope=data.vehicle_scope.model_dump(exclude={"demo_only"});db.add(KnowledgeItem(source_id=src.id,dtc_id=dtc.id,system=entry.system,component=str(structured.get("component","unspecified_demo")),item_type=typ,title=title,content=f"[DÉMO] {title}",structured_data={**structured,"demo_only":True,"compatibility_scope":scope},confidence_level="demo",human_verified=data.source.review_status=="reviewed")); count+=1
        db.commit(); return {"imported":True,"duplicate":False,"source_id":src.id,"checksum":checksum,"items_created":count,"warnings":["Corpus fictif uniquement."]}
    except Exception:
        db.rollback(); raise
