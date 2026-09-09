from sqlalchemy import select

from app.database.models import (
    DiagnosticContribution,
    DiagnosticEvent,
    DiagnosticSession,
    DiagnosticTroubleCode,
    DTCSubmission,
    Garage,
    GarageMembership,
    User,
    VehicleProfile,
)
from app.database.session import SessionLocal


def vehicle_id(client):
    response = client.get("/api/vehicles")
    assert response.status_code == 200
    return response.json()["items"][0]["id"]


def create_case(client, symptoms="Ratés moteur"):
    response = client.post("/api/diagnostics", json={"vehicle_id": vehicle_id(client), "mileage": 125000, "symptoms": symptoms, "circumstances": "Moteur chaud"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def completion_payload(**changes):
    payload = {
        "resolution_status": "problem_repaired",
        "confirmed_cause": "Bobine d’allumage cylindre 1",
        "selected_hypothesis_id": None,
        "repair_action_type": "component_replaced",
        "repair_action_details": "Bobine remplacée",
        "components_involved": ["Bobine cylindre 1"],
        "root_cause_confidence": "successful_repair",
        "post_repair_result": "resolved",
        "dtc_after_repair": "cleared_no_return",
        "technician_notes": "Essai routier concluant",
    }
    payload.update(changes)
    return payload


def test_cross_garage_case_cannot_be_completed(client):
    with SessionLocal() as db:
        garage = Garage(name="Autre garage")
        db.add(garage); db.flush()
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        vehicle = VehicleProfile(garage_id=garage.id, make="Ford", model="Focus", year=2020, market="EU", engine_name="EcoBoost", engine_code="M1DA", fuel_type="gasoline", transmission="manual", notes="")
        db.add(vehicle); db.flush()
        case = DiagnosticSession(garage_id=garage.id, technician_id=user.id, vehicle_profile_id=vehicle.id, status="draft")
        db.add(case); db.commit(); other_case_id = case.id
    assert client.post(f"/api/diagnostics/{other_case_id}/complete", json=completion_payload()).status_code == 404


def test_completion_persists_and_preserves_events(client):
    case_id = create_case(client)
    with SessionLocal() as db:
        db.add(DiagnosticEvent(session_id=case_id, event_type="EvidenceAdded", payload={"value": 12}, actor_type="user")); db.commit()
    response = client.post(f"/api/diagnostics/{case_id}/complete", json=completion_payload())
    assert response.status_code == 201
    with SessionLocal() as db:
        case = db.get(DiagnosticSession, case_id)
        events = db.scalars(select(DiagnosticEvent).where(DiagnosticEvent.session_id == case_id).order_by(DiagnosticEvent.created_at)).all()
        assert case.status == "completed" and case.completed_at
        assert [event.event_type for event in events] == ["EvidenceAdded", "DiagnosticCompleted"]
    assert client.post(f"/api/diagnostics/{case_id}/complete", json=completion_payload()).status_code == 409


def test_consent_false_creates_no_contribution(client):
    case_id = create_case(client)
    assert client.post(f"/api/diagnostics/{case_id}/consent", json={"consent": False}).status_code == 201
    response = client.post(f"/api/diagnostics/{case_id}/complete", json=completion_payload())
    assert response.json()["contribution"] is None
    with SessionLocal() as db:
        assert not db.scalar(select(DiagnosticContribution).where(DiagnosticContribution.session_id == case_id))


def test_consent_true_creates_sanitized_pending_contribution(client):
    symptoms = "Ratés, VIN WVWZZZ1JZXW000001, AB-123-CD, client@example.com, +33 6 12 34 56 78"
    case_id = create_case(client, symptoms)
    client.post(f"/api/diagnostics/{case_id}/fault-codes", json={"fault_codes": [{"code": "P0301", "namespace": "sae_obd2", "ecu": "PCM", "status": "active", "freeze_frame": {"rpm": 850}, "technician_verification": "confirmed"}]})
    assert client.post(f"/api/diagnostics/{case_id}/consent", json={"consent": True}).status_code == 201
    response = client.post(f"/api/diagnostics/{case_id}/complete", json=completion_payload())
    assert response.status_code == 201
    contribution = response.json()["contribution"]
    assert contribution["status"] == "PENDING_REVIEW" and contribution["source_type"] == "WORKSHOP_CASE"
    serialized = str(contribution["sanitized_payload"])
    for secret in ("WVWZZZ1JZXW000001", "AB-123-CD", "client@example.com", "+33 6 12 34 56 78"):
        assert secret not in serialized


def test_dtc_submission_is_pending_and_never_changes_trusted_data(client):
    payload = {"code": "P0301", "manufacturer": "Volkswagen", "ecu_module": "PCM", "description": "Raté cylindre observé", "attested": True}
    with SessionLocal() as db:
        trusted = db.scalar(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.code == "P0301"))
        original = trusted.generic_description if trusted else None
    response = client.post("/api/dtc-submissions", json=payload)
    assert response.status_code == 201 and response.json()["submission"]["status"] == "PENDING_REVIEW"
    with SessionLocal() as db:
        row = db.scalar(select(DTCSubmission).where(DTCSubmission.code == "P0301"))
        assert row and row.status == "PENDING_REVIEW"
        trusted = db.scalar(select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.code == "P0301"))
        assert (trusted.generic_description if trusted else None) == original


def test_dashboard_metrics_and_complete_flow(client):
    case_id = create_case(client)
    assert client.post(f"/api/diagnostics/{case_id}/fault-codes", json={"fault_codes": [{"code": "P0301", "namespace": "sae_obd2", "ecu": "PCM", "technician_verification": "confirmed"}]}).status_code == 201
    assert client.post(f"/api/diagnostics/{case_id}/measurements", json={"name": "Tension bobine", "value": "12.4", "unit": "V", "conditions": "contact", "source": "manual"}).status_code == 201
    assert client.post(f"/api/diagnostics/{case_id}/consent", json={"consent": True}).status_code == 201
    assert client.post(f"/api/diagnostics/{case_id}/complete", json=completion_payload()).status_code == 201
    dashboard = client.get("/api/workspace/dashboard").json()
    assert dashboard["metrics"] == {
        **dashboard["metrics"],
        "total_diagnostics": 1,
        "completed_diagnostics": 1,
        "active_diagnostics": 0,
        "resolved_diagnostics": 1,
        "unique_dtcs": 1,
        "cases_shared": 1,
    }
    assert dashboard["recent_diagnostics"][0]["id"] == case_id


def test_technician_cannot_access_admin_review(client):
    technician = client.__class__(client.app, raise_server_exceptions=True)
    login = technician.post("/api/auth/login", json={"email": "technician@example.com", "password": "demo-tech-change-me"})
    assert login.status_code == 200
    assert technician.get("/api/admin/review").status_code == 403
