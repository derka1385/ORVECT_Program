import io

import pytest
from fastapi import FastAPI,Request
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings,settings
from app.auth import verify_password
from app.database.models import DiagnosticHypothesis,DiagnosticSession,DiagnosticTroubleCode,EcuConfiguration,User,VehicleConfiguration,VehicleConfigurationCandidate,VehicleProfile,VehicleResolutionEvent,VinResolutionRequest
from app.database.session import SessionLocal
from app.main import PayloadLimitMiddleware,app
from app.modules.diagnostic_ai import analysis_service
from app.modules.diagnostic_ai.diagnostic_engine import DiagnosticEngine
from app.modules.diagnostic_ai.providers import AIInvalidResponse,ProviderResult,_gemini_response_schema,_mock_analysis,validate_provider_sources
from app.modules.diagnostic_ai.schemas import LLMDiagnosticAnalysis
from app.modules.diagnostic_ai.safety_engine import SafetyEngine
from app.seed import ADMIN_USER_ID,GOLF_VEHICLE_ID,VEHICLE_ID,seed


def test_authentication_is_required_and_garage_header_is_ignored(client):
    unauthenticated=TestClient(app)
    assert unauthenticated.get("/api/health").status_code==200
    assert unauthenticated.get("/api/vehicles").status_code==401
    response=client.get("/api/vehicles",headers={"X-Garage-ID":"attacker-selected-garage"})
    assert response.status_code==200
    assert VEHICLE_ID in {item["id"] for item in response.json()["items"]}


def test_development_demo_mode_needs_no_account_and_exposes_golf(monkeypatch):
    monkeypatch.setattr(settings,"app_environment","development")
    monkeypatch.setattr(settings,"demo_access_without_login",True)
    anonymous=TestClient(app)
    response=anonymous.get("/api/vehicles")
    assert response.status_code==200
    golf=next(item for item in response.json()["items"] if item["id"]==GOLF_VEHICLE_ID)
    assert (golf["make"],golf["model"],golf["engine_code"])==("Volkswagen","Golf VII","CZCA")
    assert anonymous.get("/api/auth/me").json()["role"]=="admin"


def test_technician_cannot_access_administrative_knowledge_routes():
    technician=TestClient(app)
    login=technician.post("/api/auth/login",json={"email":"technician@example.com","password":"demo-tech-change-me"})
    assert login.status_code==200
    assert technician.get("/api/knowledge/items").status_code==403


def test_active_dtc_catalog_contains_no_approximations_and_p1351_is_safe(client):
    listing=client.get("/api/dtcs?page=1&page_size=100")
    assert listing.status_code==200 and listing.json()["total"]==8920
    assert all(item["definition_type"]=="generic_standardized" for item in listing.json()["items"])
    assert all({"source_id","source_type","source_version","vehicle_compatibility","timestamp","verified"}<=set(item["source"]) for item in listing.json()["items"])
    p1351=client.get("/api/dtcs/P1351")
    assert p1351.status_code==200
    assert p1351.json()["definition_type"]=="manufacturer_specific"
    assert p1351.json()["generic_description"]=="Definition unavailable for this vehicle configuration."
    assert p1351.json()["documented"] is False and p1351.json()["source"] is None
    db=SessionLocal()
    try:
        assert db.scalar(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.code=="P1351")) is None
        assert not db.scalars(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.confidence_tier=="approximation_family")).all()
    finally:db.close()


def test_llm_schema_has_no_safety_decision_and_allows_zero_hypotheses():
    schema=_gemini_response_schema()
    assert "safetyAssessment" not in schema["properties"]
    assert schema["properties"]["hypotheses"].get("minItems") is None


def test_diagnostic_engine_forces_zero_hypotheses_until_evidence_is_sufficient():
    base={"vehicle":{"configuration_confirmed":True,"engine_code":"DEMO"},"technical_definitions":[{"definition_type":"generic_standardized","documented":True}],"fault_codes":[{"code":"P0301","freeze_frame":{}}],"measurements":[],"previous_steps":[],"untrusted_user_data":{"symptoms":""},"images":[]}
    gate=DiagnosticEngine().evaluate(base)
    assert gate.hypotheses_allowed is False and gate.required_status=="insufficient_evidence"
    manufacturer=DiagnosticEngine().evaluate({**base,"technical_definitions":[{"definition_type":"manufacturer_specific","documented":False}]})
    assert manufacturer.hypotheses_allowed is False and manufacturer.required_status=="manufacturer_specific_definition_unavailable"
    informed=DiagnosticEngine().evaluate({**base,"measurements":[{"name":"voltage","value":12.4}]})
    assert informed.hypotheses_allowed is True and informed.required_status is None
    symptom_informed=DiagnosticEngine().evaluate({**base,"untrusted_user_data":{"symptoms":"Loss of power under load"}})
    assert symptom_informed.hypotheses_allowed is True and symptom_informed.reasons==["reported_symptoms_available"]


def test_safety_engine_defaults_to_human_review_and_uses_only_its_rules():
    unknown=SafetyEngine().assess({"fault_codes":[{"code":"P0301","status":"active"}],"untrusted_user_data":{}})
    assert unknown.status=="UNKNOWN" and unknown.humanReviewRequired is True and unknown.ruleIds==["safety-rules-v1:no-matching-rule"]
    stopped=SafetyEngine().assess({"fault_codes":[{"code":"P0524","status":"active"}],"untrusted_user_data":{}})
    assert stopped.status=="STOP_AS_SOON_AS_SAFE" and stopped.decisionSource=="safety_engine"
    misfire=SafetyEngine().assess({"fault_codes":[],"untrusted_user_data":{"symptoms":"engine misfire"}})
    assert misfire.status=="UNKNOWN"


def test_explanation_layer_cannot_emit_critical_decisions():
    context={"fault_codes":[{"code":"P1351"}],"technical_definitions":[{"code":"P1351","description":"Definition unavailable for this vehicle configuration.","definition_type":"manufacturer_specific","documented":False,"source":None}]}
    analysis=_mock_analysis(context)
    unsafe=analysis.model_copy(update={"caseSummary":"The vehicle is safe to drive."})
    with pytest.raises(AIInvalidResponse):
        validate_provider_sources(unsafe,context)


def test_production_configuration_fails_without_vin_keys():
    with pytest.raises(ValidationError):
        Settings(_env_file=None,app_environment="production",vin_encryption_key="",vin_fingerprint_secret="",development_secret="production-secret",demo_admin_password="",demo_technician_password="")


@pytest.mark.parametrize("database_url", ["postgres://user:pass@host/database", "postgresql://user:pass@host/database"])
def test_postgres_database_urls_use_installed_psycopg_driver(database_url):
    configured=Settings(_env_file=None,database_url=database_url)
    assert configured.database_url=="postgresql+psycopg://user:pass@host/database"


def test_production_bootstrap_password_requires_email_and_minimum_length():
    base={"_env_file":None,"app_environment":"production","vin_encryption_key":"vin-key","vin_fingerprint_secret":"fingerprint-secret","development_secret":"production-secret","demo_admin_password":"","demo_technician_password":""}
    with pytest.raises(ValidationError):
        Settings(**base,bootstrap_admin_password="long-enough-password")
    with pytest.raises(ValidationError):
        Settings(**base,bootstrap_admin_email="owner@example.com",bootstrap_admin_password="too-short")


def test_seed_bootstrap_password_is_applied_only_when_password_is_missing(monkeypatch):
    with SessionLocal() as db:
        admin=db.get(User,ADMIN_USER_ID)
        admin.password_hash=None
        db.commit()
        monkeypatch.setattr(settings,"bootstrap_admin_email","owner@example.com")
        monkeypatch.setattr(settings,"bootstrap_admin_password","first-bootstrap-password")
        seed(db)
        db.refresh(admin)
        original_hash=admin.password_hash
        assert admin.email=="owner@example.com" and verify_password("first-bootstrap-password",original_hash)
        monkeypatch.setattr(settings,"bootstrap_admin_password","replacement-bootstrap-password")
        seed(db)
        db.refresh(admin)
        assert admin.password_hash==original_hash


def test_direct_vin_is_encrypted_and_vehicle_delete_cascades(client,tmp_path,monkeypatch):
    monkeypatch.setattr(settings,"diagnostic_image_dir",str(tmp_path))
    created=client.post("/api/vehicles",json={"make":"Honda","model":"Accord","year":2003,"engine_name":"Demo","engine_code":"DEMO","vin":"1HGCM82633A004352","is_demo_vehicle":True})
    assert created.status_code==201 and "vin" not in created.json() and "vin_encrypted" not in created.json()
    vehicle_id=created.json()["id"]
    session=client.post("/api/diagnostic-sessions",json={"vehicle_profile_id":vehicle_id}).json()
    case=client.post("/api/diagnostics",json={"vehicle_id":vehicle_id}).json()
    image=io.BytesIO();Image.new("RGB",(4,4),"white").save(image,"PNG")
    assert client.post(f"/api/diagnostics/{case['id']}/images",files={"files":("evidence.png",image.getvalue(),"image/png")}).status_code==201
    exposed=client.get(f"/api/vehicles/{vehicle_id}").json()
    assert not {"vin","vin_encrypted","vin_fingerprint"}&set(exposed)
    db=SessionLocal()
    try:
        vehicle=db.get(VehicleProfile,vehicle_id)
        assert vehicle.vin is None and vehicle.vin_encrypted and vehicle.vin_fingerprint and vehicle.vin_last_six=="004352"
        resolution=VinResolutionRequest(garage_id=vehicle.garage_id,vehicle_id=vehicle.id,vin_encrypted="test-ciphertext",vin_fingerprint="f"*64,vin_last_six="004352",selected_provider="test",status="confirmed")
        db.add(resolution);db.flush()
        candidate=VehicleConfigurationCandidate(resolution_id=resolution.id,provider_name="test")
        configuration=VehicleConfiguration(vehicle_id=vehicle.id,confirmed_by_user=True)
        event=VehicleResolutionEvent(resolution_id=resolution.id,vehicle_id=vehicle.id,event_type="test",payload={},actor_type="system")
        db.add_all([candidate,configuration,event]);db.flush()
        ecu=EcuConfiguration(vehicle_configuration_id=configuration.id,ecu_type="engine",source="test")
        db.add(ecu);db.commit()
        associated_ids=(resolution.id,candidate.id,configuration.id,event.id,ecu.id)
    finally:db.close()
    assert client.delete(f"/api/vehicles/{vehicle_id}").status_code==204
    assert not list(tmp_path.iterdir())
    db=SessionLocal()
    try:
        assert db.get(VehicleProfile,vehicle_id) is None and db.get(DiagnosticSession,session["id"]) is None
        for model,identifier in zip((VinResolutionRequest,VehicleConfigurationCandidate,VehicleConfiguration,VehicleResolutionEvent,EcuConfiguration),associated_ids):
            assert db.get(model,identifier) is None
    finally:db.close()


def test_image_pixel_limit_is_enforced_before_full_processing(client,tmp_path,monkeypatch):
    monkeypatch.setattr(settings,"diagnostic_image_dir",str(tmp_path));monkeypatch.setattr(settings,"max_image_pixels",50)
    case=client.post("/api/diagnostics",json={"vehicle_id":VEHICLE_ID}).json()
    output=io.BytesIO();Image.new("RGB",(10,10),"white").save(output,"PNG")
    response=client.post(f"/api/diagnostics/{case['id']}/images",files={"files":("large.png",output.getvalue(),"image/png")},data={"category":"engine_bay"})
    assert response.status_code==415 and not list(tmp_path.iterdir())


def test_verified_legacy_hypotheses_retain_complete_source_references(client):
    session=client.post("/api/diagnostic-sessions",json={"vehicle_profile_id":VEHICLE_ID}).json()
    client.post(f"/api/diagnostic-sessions/{session['id']}/observations",json={"observation_type":"DTC","key":"P0301","value":{"status":"confirmed"}})
    assert client.post(f"/api/diagnostic-sessions/{session['id']}/analyze").status_code==200
    db=SessionLocal()
    try:
        hypothesis=db.scalar(select(DiagnosticHypothesis).where(DiagnosticHypothesis.session_id==session["id"]))
        reference=hypothesis.source_references[0]
        assert hypothesis.source_ids==[reference["source_id"]]
        assert {"source_id","source_type","source_version","vehicle_compatibility","timestamp","verified"}<=set(reference)
    finally:db.close()


def test_ai_hypothesis_persistence_keeps_complete_source_references(client,monkeypatch):
    class SourcedProvider:
        async def analyze_initial_case(self,context,images):
            payload=_mock_analysis(context).model_dump(mode="json")
            source=next(item for item in context["technical_definitions"] if item["code"]=="P0301")["source"]
            payload["hypotheses"]=[{
                "id":"source-persistence-check","label":"Test-only sourced hypothesis","component":"ignition",
                "confidence":0.5,"supportingEvidence":["P0301 is present"],"contradictingEvidence":[],
                "requiredConfirmation":["Independent physical confirmation is required"],"status":"possible",
                "verificationStatus":"partially_verified","sources":[source],
            }]
            return ProviderResult(LLMDiagnosticAnalysis.model_validate(payload),"test","source-persistence",1)

    case=client.post("/api/diagnostics",json={"vehicle_id":VEHICLE_ID}).json()
    client.post(f"/api/diagnostics/{case['id']}/fault-codes",json={"fault_codes":[{"code":"P0301","technician_verification":"confirmed"}]})
    client.post(f"/api/diagnostics/{case['id']}/measurements",json={"name":"test evidence","value":12.4,"unit":"V"})
    monkeypatch.setattr(analysis_service,"get_ai_provider",lambda:SourcedProvider())
    assert client.post(f"/api/diagnostics/{case['id']}/analyze").status_code==200
    db=SessionLocal()
    try:
        hypothesis=db.scalar(select(DiagnosticHypothesis).where(DiagnosticHypothesis.session_id==case["id"],DiagnosticHypothesis.title=="Test-only sourced hypothesis"))
        reference=hypothesis.source_references[0]
        assert hypothesis.source_ids==[reference["source_id"]]
        assert {"source_id","source_type","source_version","vehicle_compatibility","timestamp","verified"}<=set(reference)
    finally:db.close()


def test_pagination_limits_are_enforced(client):
    page=client.get("/api/vehicles?page=1&page_size=1")
    assert page.status_code==200 and set(page.json())=={"items","page","page_size","total"}
    assert client.get(f"/api/vehicles?page_size={settings.max_page_size+1}").status_code==422


def test_collection_and_case_limits_are_enforced(client,monkeypatch):
    session=client.post("/api/diagnostic-sessions",json={"vehicle_profile_id":VEHICLE_ID}).json()
    monkeypatch.setattr(settings,"max_diagnostic_observations",0)
    assert client.post(f"/api/diagnostic-sessions/{session['id']}/observations",json={"observation_type":"note","key":"limit","value":{}}).status_code==413
    assert set(client.get(f"/api/diagnostic-sessions/{session['id']}/hypotheses?page_size=1").json())=={"items","page","page_size","total"}
    assert set(client.get(f"/api/diagnostic-sessions/{session['id']}/steps?page_size=1").json())=={"items","page","page_size","total"}

    case=client.post("/api/diagnostics",json={"vehicle_id":VEHICLE_ID}).json()
    monkeypatch.setattr(settings,"max_diagnostic_fault_codes",1)
    assert client.post(f"/api/diagnostics/{case['id']}/fault-codes",json={"fault_codes":[{"code":"P0301"},{"code":"P0351"}]}).status_code==413
    monkeypatch.setattr(settings,"max_diagnostic_measurements",0)
    assert client.post(f"/api/diagnostics/{case['id']}/measurements",json={"name":"pressure","value":1}).status_code==413


def test_payload_limit_rejects_declared_body_before_endpoint_execution():
    limited=FastAPI()
    executed={"value":False}
    @limited.post("/")
    async def consume(request:Request):
        executed["value"]=True
        await request.body()
        return {"ok":True}
    limited.add_middleware(PayloadLimitMiddleware,limit=4)
    with TestClient(limited) as local:
        assert local.post("/",content=b"12345").status_code==413
    assert executed["value"] is False
