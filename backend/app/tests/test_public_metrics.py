from fastapi.testclient import TestClient

from app.database.models import AICall
from app.database.session import SessionLocal
from app.main import app
from app.seed import VEHICLE_ID


def create_analyzed_diagnostic(client):
    response=client.post(
        "/api/diagnostics",
        json={
            "vehicle_id":VEHICLE_ID,
            "mileage":120000,
            "symptoms":"Voyant moteur et ratés",
            "circumstances":"Moteur chaud",
        },
    )
    assert response.status_code==201,response.text
    case_id=response.json()["id"]
    response=client.post(
        f"/api/diagnostics/{case_id}/fault-codes",
        json={"fault_codes":[{
            "code":"P0301",
            "ecu":"ECU moteur",
            "status":"active",
            "freeze_frame":{},
            "technician_verification":"confirmed",
        }]},
    )
    assert response.status_code==201,response.text
    assert client.post(f"/api/diagnostics/{case_id}/analyze").status_code==200
    return case_id


def test_public_metrics_counts_each_successfully_analyzed_diagnostic_once(client):
    anonymous=TestClient(app,raise_server_exceptions=True)
    initial=anonymous.get("/api/public/metrics")
    assert initial.status_code==200
    assert initial.json()=={
        "diagnostics_analyzed":0,
        "counting_rule":"one_per_diagnostic_after_first_successful_analysis",
    }

    case_id=create_analyzed_diagnostic(client)
    assert anonymous.get("/api/public/metrics").json()["diagnostics_analyzed"]==1

    with SessionLocal() as db:
        first=db.query(AICall).filter(AICall.session_id==case_id).one()
        db.add(AICall(
            session_id=case_id,
            provider=first.provider,
            model=first.model,
            operation_type="follow_up_analysis",
            status="completed",
            schema_version=first.schema_version,
            prompt_version=first.prompt_version,
            request_id="public-metrics-repeat",
            input_hash="repeat-analysis",
            output_hash=first.output_hash,
            output_payload=first.output_payload,
            validation_status="valid",
            error_safe=None,
            latency_ms=1,
            token_usage=None,
        ))
        db.commit()

    repeated=anonymous.get("/api/public/metrics")
    assert repeated.json()["diagnostics_analyzed"]==1
    assert repeated.headers["cache-control"]=="public, max-age=15, stale-while-revalidate=60"

    create_analyzed_diagnostic(client)
    assert anonymous.get("/api/public/metrics").json()["diagnostics_analyzed"]==2
