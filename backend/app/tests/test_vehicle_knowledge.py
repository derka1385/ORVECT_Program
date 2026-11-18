import pytest

from app.database.models import EngineVariant, ReportedVehicleIssue, VehicleGeneration
from app.database.session import SessionLocal
from app.modules.diagnostic_ai.schemas import SourceReference
from app.modules.vehicle_knowledge import service


@pytest.fixture
def db():
    session = SessionLocal()
    assert service.load_reference_data(session), "data/vehicle_knowledge manquant"
    session.commit()
    yield session
    session.close()


def test_engine_tokens_and_scope_rules():
    assert service.engine_tokens("EB2ADT / HN05") == ["EB2ADT", "HN05"]
    assert service.engine_tokens("K9KU8??") == ["K9KU8"]
    belt = {"makes": ["PEUGEOT"], "engine_code_regex": "^HN[A-Z0-9]", "engine_code_exclude_regex": "^(HN09|HP[XY])$"}
    assert service.scope_matches(belt, {"make": "Peugeot", "engine_code": "HNZ / HN01"})
    assert not service.scope_matches(belt, {"make": "Peugeot", "engine_code": "HPY/HN09"})  # PureTech 2023 à chaîne
    assert not service.scope_matches(belt, {"make": "Renault", "engine_code": "HNZ"})
    assert not service.scope_matches(belt, {"make": "Peugeot", "engine_code": None})  # code inconnu : on ne suppose rien


def test_reference_data_resolves_generation_variant_and_issues(db):
    assert db.query(VehicleGeneration).count() > 700
    assert db.query(EngineVariant).count() > 5000
    assert db.query(ReportedVehicleIssue).filter_by(origin="web_research").count() >= 40
    assert not service.load_reference_data(db)  # même checksum : pas de rechargement

    gen, variant, basis = service.resolve(db, "Volkswagen", "Golf", 2015, "CZCA", "WVWZZZAUZFW123456")
    assert gen.id == "vw-golf-au" and variant.engine_code == "CZC"
    assert "préfixe VIN homologué" in basis and "code moteur homologué" in basis

    vehicle = {"make": "Peugeot", "model": "208", "model_year": 2015, "engine_code": "HNZ / HN01"}
    gen, variant, _ = service.resolve(db, **{k: vehicle[k] for k in ("make", "model", "model_year", "engine_code")})
    assert gen.id == "peugeot-208-c"
    ids = [i["id"] for i in service.find_issues(db, vehicle, gen, variant, [], "perte de puissance voyant huile")]
    assert "psa-eb2t-courroie-humide" in ids

    clio = {"make": "Renault", "model": "Clio", "model_year": 2014, "engine_code": "H5FG4??"}
    gen, variant, _ = service.resolve(db, **clio)
    issues = service.find_issues(db, clio, gen, variant, ["P0303"], "ratés")
    assert issues[0]["id"] == "renault-h5ft-consommation-huile" and issues[0]["matched_dtc_codes"] == ["P0303"]


def test_owner_complaints_and_eu_recalls(db):
    assert db.query(ReportedVehicleIssue).filter_by(origin="safety_gate").count() > 1000
    focus = {"make": "Ford", "model": "Focus", "model_year": 2014, "engine_code": "PNDA"}
    gen, variant, _ = service.resolve(db, **focus)
    issues = service.find_issues(db, focus, gen, variant, [], "tremblements au démarrage")
    complaints = [i for i in issues if i["origin"] == "nhtsa_complaints"]
    assert complaints and complaints[0]["trust_class"] == "web_field_signal"
    # un motif « diesel » ne remonte pas sur une variante essence connue
    assert not any("diesel" in i["title"] for i in complaints)


def test_reported_issue_is_a_valid_unverified_citation(db):
    vehicle = {"make": "Peugeot", "model": "208", "model_year": 2015, "engine_code": "HNZ / HN01"}
    block = service.for_case(db, vehicle, [], "voyant huile")
    assert block["vehicle_reference"]["engine_variant"]["engine_code"].startswith("HNZ")
    excerpt = block["reported_issues"][0]
    source = SourceReference.model_validate(excerpt["source"])
    assert source.verified is False and source.source_id == excerpt["id"]
    assert excerpt["origin"] == "orvect_reported_issues"


def test_lookup_route(client):
    SessionLocal().close()
    with SessionLocal() as session:
        service.load_reference_data(session)
        session.commit()
    response = client.post("/api/vehicle-knowledge/lookup", json={
        "vin": "WVWZZZAUZFW123456", "make": "VW", "model": "Golf", "model_year": 2015, "engine_code": "CZCA"})
    assert response.status_code == 200
    body = response.json()
    assert body["vehicle_reference"]["generation"] == "vw-golf-au"
    assert body["vehicle_reference"]["engine_variant"]["engine_code"] == "CZC"
    assert any(i["id"] == "vag-ea211-boitier-pompe-thermostat" for i in body["reported_issues"])
