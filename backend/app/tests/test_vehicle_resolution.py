import asyncio,json
import httpx
from sqlalchemy import select
from app.database.models import AICall,VehicleResolutionEvent,VinResolutionRequest
from app.database.session import SessionLocal
from app.modules.vehicle_resolution.domain.exceptions import ProviderResponseError,ProviderUnavailableError
from app.modules.vehicle_resolution.providers.nhtsa_vpic_provider import NhtsaVpicProvider
from app.modules.vehicle_resolution.services.vin_validator import VinValidator

VIN_A="ZZZTESTA0DEMA0001"; VIN_B="ZZZTESTB0DEMB0002"; VIN_C="ZZZTESTC0DEMC0003"; VIN_D="ZZZTESTD0DEMD0004"; VIN_E="ZZZTESTE0DEME0005"

def test_validator_normalizes_and_checks_formats():
    service=VinValidator()
    assert service.validate(" zzz-testa0 dema0001 ").normalized_vin==VIN_A
    assert service.validate(VIN_A).check_digit_status=="not_applicable"
    assert service.validate("1HGCM82633A004352").check_digit_status=="valid"
    assert not service.validate("VIN-I-O-Q").is_valid_format
    assert service.validate("ZZZTEST*").warnings

def test_scenarios_candidates_cache_and_degraded_mode(client):
    a=client.post("/api/vehicle-resolution/vin",json={"vin":VIN_A,"country_code":"FR"}).json()
    assert a["status"]=="requires_confirmation" and len(a["candidates"])==1
    assert a["masked_vin"].endswith("MA0001") and VIN_A not in json.dumps(a)
    assert a["candidates"][0]["field_provenance"]["engine_code"]["origin"]=="provider"
    cached=client.post("/api/vehicle-resolution/vin",json={"vin":VIN_A}).json()
    assert cached["id"]==a["id"] and cached["cache_hit"] is True
    b=client.post("/api/vehicle-resolution/vin",json={"vin":VIN_B}).json()
    assert "engine_code" in b["candidates"][0]["missing_critical_fields"]
    c=client.post("/api/vehicle-resolution/vin",json={"vin":VIN_C}).json()
    assert len(c["candidates"])==2
    e=client.post("/api/vehicle-resolution/vin",json={"vin":VIN_E}).json()
    assert e["status"]=="provider_failed" and not e["candidates"]

def test_confirmation_correction_precision_ecu_conflict_and_isolation(client):
    result=client.post("/api/vehicle-resolution/vin",json={"vin":VIN_D}).json(); candidate=result["candidates"][0]
    confirmed=client.post(f"/api/vehicle-resolution/{result['id']}/confirm",json={"candidate_id":candidate["id"],"corrections":{"engine_name":"2.0 Diesel confirmé"}})
    assert confirmed.status_code==200
    payload=confirmed.json(); vehicle_id=payload["vehicle"]["id"]
    assert payload["configuration"]["precision_level"]=="variant_specific"
    ecu=client.post(f"/api/vehicles/{vehicle_id}/ecu-configurations",json={"ecu_type":"engine","part_number":"DEMO-ECU-44","calibration_id":"CAL-44","reported_engine_code":"CONFLICT"}).json()
    assert ecu["conflict"] is True and ecu["precision_level"]=="unknown"
    other=client.get(f"/api/vehicle-resolution/{result['id']}",headers={"X-Garage-ID":"other"})
    assert other.status_code==200

def test_vin_to_p0301_compatibility_and_no_vin_in_audit_or_llm(client):
    result=client.post("/api/vehicle-resolution/vin",json={"vin":VIN_A}).json()
    confirmed=client.post(f"/api/vehicle-resolution/{result['id']}/confirm",json={"candidate_id":result["candidates"][0]["id"]}).json(); vehicle_id=confirmed["vehicle"]["id"]
    match=client.post(f"/api/vehicles/{vehicle_id}/diagnostic-compatibility",json={"dtcs":["P0301","P1351"]}).json()
    assert {x["code"] for x in match["matched_definitions"]}=={"P0301"}
    assert {x["code"] for x in match["unavailable_definitions"]}=={"P1351"}
    assert match["matched_knowledge_packs"] and match["precision_level"]=="variant_specific"
    session=client.post("/api/diagnostic-sessions",json={"vehicle_profile_id":vehicle_id,"customer_complaint":"Test E2E VIN P0301"}).json()
    client.post(f"/api/diagnostic-sessions/{session['id']}/observations",json={"observation_type":"DTC","key":"P0301","value":{"status":"confirmed"},"source":"manual_entry"})
    analysis=client.post(f"/api/diagnostic-sessions/{session['id']}/analyze")
    assert analysis.status_code==200
    db=SessionLocal()
    try:
        row=db.scalar(select(VinResolutionRequest).where(VinResolutionRequest.id==result["id"]))
        assert row.vin_encrypted != VIN_A and row.vin_fingerprint != VIN_A
        events=db.scalars(select(VehicleResolutionEvent).where(VehicleResolutionEvent.resolution_id==result["id"])).all()
        assert VIN_A not in json.dumps([x.payload for x in events])
        assert all(VIN_A not in (x.input_hash or "") for x in db.scalars(select(AICall)).all())
    finally:db.close()

def test_nhtsa_provider_success_empty_invalid_and_timeout():
    async def success(request):return httpx.Response(200,json={"Results":[{"Make":"HONDA","Model":"Civic","ModelYear":"2020","DisplacementL":"1.5"}]})
    client=httpx.AsyncClient(transport=httpx.MockTransport(success)); result=asyncio.run(NhtsaVpicProvider(client).decode("1HGCM82633A004352")); asyncio.run(client.aclose())
    assert result.status=="success"
    async def empty(request):return httpx.Response(200,json={"Results":[]})
    client=httpx.AsyncClient(transport=httpx.MockTransport(empty)); result=asyncio.run(NhtsaVpicProvider(client).decode("1HGCM82633A004352")); asyncio.run(client.aclose()); assert result.status=="no_match"
    async def invalid(request):return httpx.Response(200,content=b"not-json")
    client=httpx.AsyncClient(transport=httpx.MockTransport(invalid))
    try:
        try:asyncio.run(NhtsaVpicProvider(client).decode("1HGCM82633A004352")); assert False
        except ProviderResponseError:pass
    finally:asyncio.run(client.aclose())
    async def timeout(request):raise httpx.ReadTimeout("timeout",request=request)
    client=httpx.AsyncClient(transport=httpx.MockTransport(timeout))
    try:
        try:asyncio.run(NhtsaVpicProvider(client).decode("1HGCM82633A004352")); assert False
        except ProviderUnavailableError:pass
    finally:asyncio.run(client.aclose())
