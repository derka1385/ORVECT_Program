import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.auth import hash_password
from app.database.models import Garage, GarageMembership, User, VehicleProfile
from app.database.session import SessionLocal
from app.main import app
from app.schemas import AIAnalysisOutput
from app.seed import VEHICLE_ID

REPORT={"schema_version":"1.0","vehicle":{"vin":None,"make":"Demo Motors","model":"DM-1","year":2020,"engine_code":"DEMO-ENG-01"},"scan":{"timestamp":"2026-01-01T10:00:00Z","tool":"manual-demo-import","dtcs":[{"code":"P0301","status":"confirmed"}],"freeze_frame":{"engine_rpm":850},"live_data":[]}}

def test_health_and_vehicle_creation(client):
    assert client.get("/api/health").json()["status"]=="ok"
    payload={"make":"Demo Two","model":"Lab","year":2022,"engine_name":"Demo engine","engine_code":"LAB-2","is_demo_vehicle":True}
    response=client.post("/api/vehicles",json=payload)
    assert response.status_code==201 and response.json()["engine_code"]=="LAB-2"

def test_valid_and_invalid_obd_import(client):
    ok=client.post("/api/imports/obd-report",json=REPORT)
    assert ok.status_code==200 and ok.json()["supported"]==["P0301"]
    invalid={**REPORT,"schema_version":"2.0"}
    bad=client.post("/api/imports/obd-report",json=invalid)
    assert bad.status_code==422 and "Rapport OBD invalide" in bad.json()["detail"]

def create_manual(client):
    s=client.post("/api/diagnostic-sessions",json={"vehicle_profile_id":VEHICLE_ID,"customer_complaint":"Ratés au ralenti"}).json()
    r=client.post(f"/api/diagnostic-sessions/{s['id']}/observations",json={"observation_type":"DTC","key":"P0301","value":{"status":"confirmed"},"source":"manual_entry"})
    assert r.status_code==201
    a=client.post(f"/api/diagnostic-sessions/{s['id']}/analyze")
    assert a.status_code==200
    AIAnalysisOutput.model_validate(a.json())
    return s["id"]

def test_p0301_fault_moves_end_to_end(client):
    sid=create_manual(client)
    assert len(client.get(f"/api/diagnostic-sessions/{sid}/hypotheses").json()["items"])>=3
    steps=client.get(f"/api/diagnostic-sessions/{sid}/steps").json()["items"]
    assert "Permuter" in steps[0]["title"]
    result=client.post(f"/api/diagnostic-sessions/{sid}/steps/{steps[0]['id']}/complete",json={"state":"positive","result_id":"fault_moved_to_cylinder_2","comment":"Défaut devenu P0302"})
    assert result.status_code==200 and "Confirmer" in result.json()["title"]
    ranked=client.get(f"/api/diagnostic-sessions/{sid}/hypotheses").json()["items"]
    assert ranked[0]["suspected_component"]=="ignition_coil_1" and ranked[0]["status"]=="strengthened"
    scores=[(item["id"],item["probability_score"],item["status"]) for item in ranked]
    current=next(item for item in client.get(f"/api/diagnostic-sessions/{sid}/steps").json()["items"] if item["status"]=="current")
    assert client.post(f"/api/diagnostic-sessions/{sid}/steps/{current['id']}/complete",json={"state":"positive","result_id":"coil_confirmed"}).status_code==200
    assert [(item["id"],item["probability_score"],item["status"]) for item in client.get(f"/api/diagnostic-sessions/{sid}/hypotheses").json()["items"]]==scores
    assert client.post(f"/api/diagnostic-sessions/{sid}/complete").status_code==200
    report=client.get(f"/api/diagnostic-sessions/{sid}/report").json()
    assert report["leading_hypothesis"]["suspected_component"]=="ignition_coil_1" and report["sources"]

def test_p0301_fault_stays_branches_to_spark_plug(client):
    sid=create_manual(client)
    step=client.get(f"/api/diagnostic-sessions/{sid}/steps").json()["items"][0]
    nxt=client.post(f"/api/diagnostic-sessions/{sid}/steps/{step['id']}/complete",json={"state":"negative","result_id":"fault_stayed_on_cylinder_1"})
    assert nxt.status_code==200 and "bougie" in nxt.json()["title"].lower()
    assert client.get(f"/api/diagnostic-sessions/{sid}/hypotheses").json()["items"][0]["suspected_component"]=="spark_plug_1"

def test_ai_output_rejects_invalid_payload():
    try:
        AIAnalysisOutput.model_validate({"summary":"invented","unexpected":"field"})
    except ValidationError:
        pass
    else:
        raise AssertionError("Une sortie IA invalide doit être refusée")

def test_garage_isolation(client):
    db=SessionLocal(); g=Garage(name="Autre garage"); db.add(g); db.flush()
    u=User(garage_id=g.id,email="other@example.com",display_name="Other",role="technician",password_hash=hash_password("other-password"))
    v=VehicleProfile(garage_id=g.id,make="Other",model="Demo",year=2020,engine_name="Other",engine_code="OTHER",market="demo",fuel_type="gasoline",transmission="manual",notes="demo",is_demo_vehicle=True)
    db.add_all([u,v]);db.flush();db.add(GarageMembership(user_id=u.id,garage_id=g.id,role="technician"));db.commit();vid=v.id;db.close()
    other=TestClient(app);assert other.post("/api/auth/login",json={"email":"other@example.com","password":"other-password"}).status_code==200
    assert [x["id"] for x in other.get("/api/vehicles",headers={"X-Garage-ID":"00000000-0000-0000-0000-000000000001"}).json()["items"]]==[vid]
    assert other.get(f"/api/vehicles/{VEHICLE_ID}").status_code==404

def test_knowledge_and_unexpected_result(client):
    items=client.get("/api/knowledge/items?dtc_code=P0301")
    assert items.status_code==200 and len(items.json()["items"])>=3
    assert {"source_id","source_type","source_version","vehicle_compatibility","timestamp","verified"}<=set(items.json()["items"][0]["source"])
    sid=create_manual(client); step=client.get(f"/api/diagnostic-sessions/{sid}/steps").json()["items"][0]
    assert client.post(f"/api/diagnostic-sessions/{sid}/steps/{step['id']}/complete",json={"state":"positive","result_id":"invented_result"}).status_code==422

def test_knowledge_import_is_transactional_and_deduplicated(client):
    payload={"schema_version":"1.0","source":{"title":"Additional demo","source_type":"internal_demo","license_type":"internal_demo","trust_level":"demo","review_status":"reviewed","version":"1.1","demo_only":True},"vehicle_scope":{"make":"Demo Motors","model":"DM-1","year_from":2020,"year_to":2020,"engine_code":"DEMO-ENG-01","demo_only":True},"dtcs":[{"code":"P0301","system":"engine_ignition","possible_causes":[{"title":"Cause additionnelle fictive","component":"demo_component"}],"test_procedures":[],"demo_only":True}]}
    first=client.post("/api/imports/knowledge",json=payload)
    assert first.status_code==200 and first.json()["items_created"]==1
    second=client.post("/api/imports/knowledge",json=payload)
    assert second.status_code==200 and second.json()["duplicate"] is True
    unsafe={**payload,"source":{**payload["source"],"demo_only":False}}
    assert client.post("/api/imports/knowledge",json=unsafe).status_code==422

def test_manufacturer_specific_p1351_uses_safe_generic_workflow(client):
    session=client.post("/api/diagnostic-sessions",json={"vehicle_profile_id":VEHICLE_ID,"customer_complaint":"Test P1351"}).json()
    client.post(f"/api/diagnostic-sessions/{session['id']}/observations",json={"observation_type":"DTC","key":"P1351","value":{"status":"confirmed"},"source":"manual_entry"})
    analysis=client.post(f"/api/diagnostic-sessions/{session['id']}/analyze")
    assert analysis.status_code==200
    body=AIAnalysisOutput.model_validate(analysis.json())
    assert "P1351" in body.summary and body.hypotheses==[]
    assert body.conclusion_status=="manufacturer_specific_definition_unavailable"
    step=client.get(f"/api/diagnostic-sessions/{session['id']}/steps").json()["items"][0]
    completed=client.post(f"/api/diagnostic-sessions/{session['id']}/steps/{step['id']}/complete",json={"state":"unavailable","result_id":"documentation_unavailable","comment":"Aucune documentation autorisée"})
    assert completed.status_code==200 and completed.json()["status"]=="blocked"
    client.post(f"/api/diagnostic-sessions/{session['id']}/complete")
    report=client.get(f"/api/diagnostic-sessions/{session['id']}/report").json()
    assert "P1351" in report["dtcs"] and report["leading_hypothesis"] is None

def test_known_non_p0301_code_uses_catalog_description(client):
    session=client.post("/api/diagnostic-sessions",json={"vehicle_profile_id":VEHICLE_ID,"customer_complaint":"Test P0351"}).json()
    client.post(f"/api/diagnostic-sessions/{session['id']}/observations",json={"observation_type":"DTC","key":"P0351","value":{"status":"confirmed"},"source":"manual_entry"})
    analysis=client.post(f"/api/diagnostic-sessions/{session['id']}/analyze")
    assert analysis.status_code==200 and "P0351" in analysis.json()["summary"]
    assert analysis.json()["recommended_next_step"]["title"]=="Valider le contexte technique de P0351"

def test_invalid_dtc_format_is_rejected(client):
    session=client.post("/api/diagnostic-sessions",json={"vehicle_profile_id":VEHICLE_ID,"customer_complaint":"Format invalide"}).json()
    client.post(f"/api/diagnostic-sessions/{session['id']}/observations",json={"observation_type":"DTC","key":"P13ZZ","value":{"status":"confirmed"},"source":"manual_entry"})
    assert client.post(f"/api/diagnostic-sessions/{session['id']}/analyze").status_code==422

@pytest.mark.parametrize("state",["inconclusive","unavailable","invalid","refused"])
def test_noninformative_step_states_never_change_probabilities(client,state):
    sid=create_manual(client);before=[(row["id"],row["probability_score"],row["status"]) for row in client.get(f"/api/diagnostic-sessions/{sid}/hypotheses").json()["items"]]
    step=client.get(f"/api/diagnostic-sessions/{sid}/steps").json()["items"][0]
    response=client.post(f"/api/diagnostic-sessions/{sid}/steps/{step['id']}/complete",json={"state":state,"comment":"Aucune preuve exploitable"})
    assert response.status_code==200 and response.json()["status"]=="blocked"
    after=[(row["id"],row["probability_score"],row["status"]) for row in client.get(f"/api/diagnostic-sessions/{sid}/hypotheses").json()["items"]]
    assert after==before
