import asyncio
import pytest
from app.core.config import settings
from app.modules.vehicle_resolution.services.vehicle_confidence import VehicleConfidence
from app.modules.vehicle_resolution.services.vehicle_merger import VehicleMerger
from app.modules.vehicle_resolution.services.vehicle_normalizer import VehicleNormalizer
from app.modules.vehicle_resolution.services.vehicle_resolver import VehicleResolver

def test_normalizes_french_registration_and_vin():
    normalizer=VehicleNormalizer()
    assert normalizer.registration(" ab-123-cd ")=="AB123CD"
    assert normalizer.vin(" vf3 abc def 12345678 ")=="VF3ABCDEF12345678"

def test_normalizes_brand_fuel_transmission_and_power_without_inventing():
    row=VehicleNormalizer().normalize({"brand":"VW","fuel":"Gazole","transmissionType":"BVM","powerKw":88},"test")
    assert row["make"]=="Volkswagen" and row["fuel_type"]=="diesel" and row["transmission_type"]=="manual"
    assert row["engine_power_hp"]==119.6 and "engine_code" not in row

def test_merges_compatible_providers_with_field_sources():
    rows=[{"provider_name":"aaa_data","provider_confidence":.9,"make":"Audi","model":"A4","engine_power_hp":150},{"provider_name":"tecalliance","provider_confidence":.95,"make":"Audi","model":"A4","generation":"B9","engine_code":"DEUA","transmission_type":"automatic"}]
    merged,sources,contradictions=VehicleMerger().merge(rows)
    assert merged["engine_code"]=="DEUA" and merged["generation"]=="B9" and len(sources)>=6 and not contradictions

@pytest.mark.parametrize("field,left,right",[("engine_code","DEUA","DESA"),("transmission_type","manual","automatic")])
def test_detects_critical_contradictions(field,left,right):
    merged,_,contradictions=VehicleMerger().merge([{"provider_name":"a",field:left},{"provider_name":"b",field:right}])
    assert field in contradictions and field not in merged

def test_confidence_requires_confirmation_when_motorization_is_missing():
    score,missing,status=VehicleConfidence().calculate({"make":"Peugeot","model":"308","model_year":2017},1,[])
    assert "engine_code" in missing and status!="resolved" and score<settings.vehicle_confidence_reliable

def test_demo_complete_registration_is_explicitly_mocked():
    result=asyncio.run(VehicleResolver().resolve_registration("DEMO-123","FR"))
    assert result["status"]=="resolved" and result["vehicle"]["engine"]["code"]=="DV6FC"
    assert result["vehicle"]["metadata"]["isMockData"] is True

def test_demo_ambiguous_registration_never_selects_silently():
    result=asyncio.run(VehicleResolver().resolve_registration("DEMOAMB","FR"))
    assert result["status"]=="confirmation_required" and len(result["alternatives"])==2

def test_unknown_demo_registration_requests_vin():
    result=asyncio.run(VehicleResolver().resolve_registration("AB123CD","FR"))
    assert result["status"]=="vin_required" and "engine_code" in result["missingCriticalFields"]

def test_normalized_routes_validate_identifiers(client):
    assert client.post("/api/vehicles/resolve-registration",json={"registration":"?","country_code":"FR"}).status_code==422
    assert client.post("/api/vehicles/resolve-vin",json={"vin":"INVALIDVIN00","country_code":"FR"}).status_code==422
    response=client.post("/api/vehicles/resolve-registration",json={"registration":"DEMO123","country_code":"FR"})
    assert response.status_code==200 and response.json()["vehicle"]["engine"]["code"]=="DV6FC"

def test_no_external_key_is_exposed_in_frontend():
    from pathlib import Path
    sources=b"\n".join(path.read_bytes() for path in (Path(__file__).parents[3]/"frontend"/"src").rglob("*") if path.is_file())
    assert b"AAA_DATA_API_KEY" not in sources and b"TECALLIANCE_API_KEY" not in sources and b"AUTO_WAYS_API_KEY" not in sources
