"""Phase 1.6 controls using authored, NON-AUTOMOTIVE fixtures.

No fixture below is evidence for the real vehicle meaning of a numeric/P-code.
Real-source integration remains blocked until acquisition rights are established.
"""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.database.models import (DiagnosticDataset, DiagnosticDefinitionVariant, DiagnosticIdentifier, DiagnosticTroubleCode,
    DiagnosticCodeAlias, DiagnosticDataConflict, DiagnosticSourceAssessment, KnowledgeSource)
from app.database.session import SessionLocal
from app.modules.diagnostic_data.admission import admission_error, assertion_hash, required_claims, source_is_usable
from app.modules.diagnostic_data.ingestion import ingest_dataset, calculate_dataset_checksum, DatasetIngestionError
from app.modules.diagnostic_data.lifecycle import promote_definition, revoke_dataset, restore_dataset, PromotionError
from app.modules.diagnostic_data.schemas import DiagnosticDatasetImport, DefinitionInput, DiagnosticResolveRequest
from app.modules.diagnostic_data.resolver import DiagnosticDataResolver
from app.modules.diagnostic_data.coverage import coverage_report
from app.tests.test_diagnostic_data import _test_source, _catalog, _test_evidence, TEST_SOURCE_ID
from app.seed import ADMIN_USER_ID
from app.seed import CATALOG_SOURCE_ID, import_dtc_catalog
from app.modules.dtc.service import resolve_dtc


def payload(name="authored-fixture", version="v1", code="99991", description="Synthetic data pipeline fixture; NOT a vehicle definition."):
    raw = {"schema_version": "1.0", "source_id": TEST_SOURCE_ID,
        "namespace": {"key": "vag_legacy", "manufacturer": "Volkswagen Group", "brand_group": "VAG", "code_system": "VAG_LEGACY"},
        "dataset": {"name": name, "version": version, "format": "structured_json", "legal_use_confirmed": True,
            "documented_available_count": 1, "content_checksum_sha256": "0"*64, "metadata": {"test_only": True}},
        "definitions": [{"code": code, "canonical_display_code": code, "code_type": "manufacturer_specific",
            "description": description, "source_version": "test-v1", "provenance": {"record_id": "authored-1",
                "document_reference": "authored-test-fixture-not-automotive", "retrieved_at": "2026-09-04T00:00:00Z"}}]}
    return seal(raw)


def seal(raw):
    obj = DiagnosticDatasetImport.model_validate(raw)
    obj.dataset.content_checksum_sha256 = calculate_dataset_checksum(obj)
    return obj


def test_rights_cleared_authored_fixture_ingestion_and_provenance():
    with SessionLocal() as db:
        _test_source(db)
        dataset = ingest_dataset(db, payload(), ADMIN_USER_ID)
        row = db.scalar(select(DiagnosticDefinitionVariant).where(DiagnosticDefinitionVariant.dataset_id == dataset.id))
        assert row.promotion_stage == "quarantined"
        assert row.source_id == TEST_SOURCE_ID and row.source_version == "test-v1"
        assert row.provenance["document_reference"] == "authored-test-fixture-not-automotive"
        assert dataset.checksum == payload().dataset.content_checksum_sha256


@pytest.mark.parametrize("category", ["research_only_proprietary", "open_source_uncertain_underlying_rights", "unknown_licence"])
def test_prohibited_or_uncertain_source_cannot_import_or_resolve(category):
    with SessionLocal() as db:
        rows, _ = _catalog(db, [{"code": "VAG-TEST-RIGHTS", "description": "Synthetic source rights test."}])
        assessment = db.scalar(select(DiagnosticSourceAssessment).where(DiagnosticSourceAssessment.source_id == TEST_SOURCE_ID))
        assessment.category = category
        db.commit()
        assert not source_is_usable(db, db.get(KnowledgeSource, TEST_SOURCE_ID))
        with pytest.raises(DatasetIngestionError, match="rights assessment"):
            ingest_dataset(db, payload(), ADMIN_USER_ID)
        assert DiagnosticDataResolver().resolve(db, "vag_uds", "VAG-TEST-RIGHTS")["documented"] is False
        assert coverage_report(db)["summary"]["production_definition_rows"] == 0


def test_mit_name_without_content_assessment_is_not_legal_confirmation(client):
    body = client.post("/api/diagnostic-data/resolve", json={"namespace": "sae_obd2", "code": "P0301"}).json()
    assert body["documented"] is True
    assert body["source_details"]["licensing"]["legal_use_confirmed"] is False
    assert body["source_details"]["licensing"]["source_category"] == "open_source_uncertain_underlying_rights"


def test_claim_confidence_cannot_transfer_from_identity_to_description():
    with SessionLocal() as db:
        rows, _ = _catalog(db, [{"code": "VAG-TEST-CLAIMS", "description": "Synthetic claim test."}])
        row = rows[0]
        provenance = dict(row.provenance)
        provenance["claims"] = {"code_existence": provenance["claims"]["code_existence"]}
        row.provenance = provenance
        db.commit()
        assert "normalized_description" in admission_error(db, row)
        assert DiagnosticDataResolver().resolve(db, "vag_uds", "VAG-TEST-CLAIMS")["documented"] is False


def test_claim_hash_must_match_actual_semantics():
    with SessionLocal() as db:
        rows, _ = _catalog(db, [{"code": "VAG-TEST-HASH", "description": "Synthetic claim test."}])
        rows[0].description = "Changed meaning, unsupported by recorded evidence."
        assert "normalized_description" in admission_error(db, rows[0])


def test_tier_b_repackaging_same_upstream_does_not_count_as_independent():
    with SessionLocal() as db:
        rows, _ = _catalog(db, [{"code": "VAG-TEST-INDEPENDENCE", "description": "Synthetic Tier B test."}])
        row = rows[0]
        row.provenance = {**row.provenance, "admission_tier": "B"}
        assert "independent" in admission_error(db, row)
        # Duplicating the same proof cannot turn one origin into two.
        row.provenance = {**row.provenance, "claims": {k: v+v for k,v in row.provenance["claims"].items()}}
        assert "independent" in admission_error(db, row)


def test_tier_c_fails_closed_without_real_vehicle_attestation():
    with SessionLocal() as db:
        rows, _ = _catalog(db, [{"code": "VAG-TEST-C", "description": "Synthetic Tier C test."}])
        rows[0].provenance = {**rows[0].provenance, "admission_tier": "C"}
        assert "Tier C" in admission_error(db, rows[0])


def test_reimport_is_idempotent_but_same_version_changed_bytes_is_rejected():
    with SessionLocal() as db:
        _test_source(db)
        first = ingest_dataset(db, payload(), ADMIN_USER_ID)
        second = ingest_dataset(db, payload(), ADMIN_USER_ID)
        assert first.id == second.id
        assert db.scalar(select(func.count()).select_from(DiagnosticDefinitionVariant)) == 1
        with pytest.raises(DatasetIngestionError, match="different content"):
            ingest_dataset(db, payload(description="Changed synthetic test wording."), ADMIN_USER_ID)


def test_source_version_upgrade_preserves_prior_source_and_evidence():
    with SessionLocal() as db:
        source = _test_source(db)
        old = ingest_dataset(db, payload(), ADMIN_USER_ID)
        new_source = KnowledgeSource(id=str(uuid4()), title="Synthetic fixture v2", source_type="internal_test",
            publisher=source.publisher, version="test-v2", license_type="internal_test", trust_level="test_only",
            review_status="reviewed", local_file_path="synthetic-fixture-v2")
        db.add(new_source)
        db.flush()
        prior = db.scalar(select(DiagnosticSourceAssessment).where(DiagnosticSourceAssessment.source_id == source.id))
        data = {c.name:getattr(prior,c.name) for c in prior.__table__.columns if c.name not in {"id","source_id","source_version","created_at","updated_at"}}
        db.add(DiagnosticSourceAssessment(source_id=new_source.id, source_version=new_source.version, **data))
        db.flush()
        raw = payload(version="v2").model_dump(mode="json")
        raw["source_id"] = new_source.id
        raw["definitions"][0]["source_version"] = new_source.version
        new = ingest_dataset(db, seal(raw), ADMIN_USER_ID)
        assert new.id != old.id and db.get(KnowledgeSource, old.source_id).version == "test-v1"
        assert db.scalar(select(func.count()).select_from(DiagnosticIdentifier)) == 1


def test_conflicting_source_import_creates_record_and_blocks_production():
    with SessionLocal() as db:
        _test_source(db)
        a = ingest_dataset(db, payload(), ADMIN_USER_ID)
        b = ingest_dataset(db, payload(name="competing-fixture", description="Different synthetic meaning."), ADMIN_USER_ID)
        conflict = db.scalar(select(DiagnosticDataConflict))
        assert conflict and conflict.competing_claims["left"]["source_version"] == "test-v1"
        row = db.scalar(select(DiagnosticDefinitionVariant).where(DiagnosticDefinitionVariant.dataset_id == a.id))
        _test_evidence(db, row)
        promote_definition(db, row, "source_matched", ADMIN_USER_ID, "Synthetic staged review")
        with pytest.raises(PromotionError, match="conflict"):
            promote_definition(db, row, "verified", ADMIN_USER_ID, "Synthetic review must abstain")
        result = DiagnosticDataResolver().resolve(db, "vag_legacy", "99991")
        assert result["status"] == "ambiguous" and result["candidates"] == []


def test_uds_failure_type_and_status_are_not_opaque_identity():
    a = DiagnosticResolveRequest(namespace="vag_uds", code="U140A 00 [039]")
    b = DiagnosticResolveRequest(namespace="vag_uds", code="U140A 00 [175]")
    assert a.code == b.code == "U140A" and a.failure_type == b.failure_type == "00"
    assert a.status_byte == 39 and b.status_byte == 175
    raw = payload().definitions[0].model_dump(mode="json")
    raw.update(code="U140A 00", canonical_display_code="U140A 00")
    assert DefinitionInput.model_validate(raw).subtype == "00"
    raw["code"] = "U140A 00 [039]"
    with pytest.raises(ValueError, match="Transient"):
        DefinitionInput.model_validate(raw)


def test_failure_type_selects_variant_but_missing_subtype_abstains():
    with SessionLocal() as db:
        _catalog(db, [{"code":"U140A", "description":"Synthetic subtype 00, not a real VAG definition.", "subtype":"00"},
            {"code":"U140A", "description":"Synthetic subtype 11, not a real VAG definition.", "subtype":"11"}])
        resolver = DiagnosticDataResolver()
        assert resolver.resolve(db,"vag_uds","U140A")["status"] == "insufficient_vehicle_configuration"
        assert resolver.resolve(db,"vag_uds","U140A 00 [039]")["description"].startswith("Synthetic subtype 00")


def test_numeric_alias_uses_only_evidence_and_collapses_concept():
    with SessionLocal() as db:
        definitions, aliases = _catalog(db, [{"code":"99991", "description":"Synthetic alias mechanics, NOT a real numeric mapping."}],
            aliases=[("99991","P0301","production")])
        report = coverage_report(db)["summary"]
        assert report["production_base_concepts"] == 1 and report["distinct_alias_edges"] == 1
        assert report["unresolved_identifiers"] == 0
        assert DiagnosticDataResolver().resolve(db,"vag_uds","99991")["generic_obd_equivalent"]["code"] == "P0301"
        aliases[0].provenance = {**aliases[0].provenance, "claims": {}}
        db.commit()
        assert DiagnosticDataResolver().resolve(db,"vag_uds","99991")["generic_obd_equivalent"] is None


def test_revocation_removes_definition_and_alias_and_reimport_cannot_restore():
    with SessionLocal() as db:
        rows, aliases = _catalog(db, [{"code":"VAG-TEST-REVOKE", "description":"Synthetic revocation test."}],
            aliases=[("VAG-TEST-REVOKE","P0301","production")])
        dataset = db.get(DiagnosticDataset, rows[0].dataset_id)
        revoke_dataset(db,dataset,ADMIN_USER_ID,"Synthetic revocation rights test")
        body = DiagnosticDataResolver().resolve(db,"vag_uds","VAG-TEST-REVOKE")
        assert body["documented"] is False and body["aliases"] == []
        assert coverage_report(db)["summary"]["production_definition_rows"] == 0
        restore_dataset(db,dataset,ADMIN_USER_ID,"Synthetic approved restoration test")
        assert DiagnosticDataResolver().resolve(db,"vag_uds","VAG-TEST-REVOKE")["documented"] is True


def test_revoked_import_replays_without_reactivation():
    with SessionLocal() as db:
        _test_source(db)
        first = ingest_dataset(db,payload(),ADMIN_USER_ID)
        revoke_dataset(db,first,ADMIN_USER_ID,"Synthetic logical rollback test")
        assert ingest_dataset(db,payload(),ADMIN_USER_ID).status == "revoked"


def test_quarantine_classification_and_identity_match_never_promote():
    script = Path(__file__).parents[3]/"scripts"/"analyze_dtc_quarantine.py"
    spec = importlib.util.spec_from_file_location("quarantine_analysis",script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entry = {"code":"P1351", "confidence_tier":"approximation_family"}
    matches = module.match_quarantine(entry,[{"code":"P1351","source_id":"external", "source_version":"v1", "record_id":"1"}])
    assert module.classify(entry) == "obviously_generated"
    assert matches[0]["automatically_promotable"] is False
    assert matches[0]["generated_archive_record_permanently_blocked"] is True


def test_source_assessment_requires_admin_and_is_version_pinned(client):
    with SessionLocal() as db:
        _test_source(db)
        db.commit()
    data = {"source_version":"wrong", "category":"open_data", "authority_level":"credible",
        "commercial_use":"allowed", "redistribution":"share_alike", "attribution_requirements":"Credit author",
        "licence_evidence":"https://example.test/licence", "provenance_notes":"Synthetic source test",
        "independent_origin":"synthetic"}
    assert client.post(f"/api/diagnostic-data/sources/{TEST_SOURCE_ID}/assessment",json=data).status_code == 409
    client.post("/api/auth/logout")
    assert client.post(f"/api/diagnostic-data/sources/{TEST_SOURCE_ID}/assessment",json=data).status_code == 401


def test_tier_b_requires_two_origins_for_every_claim():
    with SessionLocal() as db:
        rows, _ = _catalog(db, [{"code":"VAG-TEST-TWO-SOURCES", "description":"Synthetic independent-source test."}])
        source = KnowledgeSource(title="Independent authored fixture",source_type="internal_test",publisher="Second fixture author",
            version="v1",license_type="internal_test",trust_level="test_only",review_status="reviewed",local_file_path="synthetic-second-source")
        db.add(source)
        db.flush()
        db.add(DiagnosticSourceAssessment(source_id=source.id,source_version="v1",category="open_data",
            authority_level="credible",commercial_use="allowed",redistribution="allowed",attribution_requirements="Test only",
            licence_evidence="Authored fixture",provenance_notes="Synthetic independent fixture",independent_origin="second-test-author",
            content_rights_confirmed=True,status="approved",assessed_by_user_id=ADMIN_USER_ID))
        row = rows[0]
        claims = {k: [*v,{**v[0],"source_id":source.id,"source_version":"v1"}] for k,v in row.provenance["claims"].items()}
        row.provenance = {**row.provenance,"admission_tier":"B","claims":claims}
        db.flush()
        assert admission_error(db,row) is None
        claims["normalized_description"] = claims["normalized_description"][:1]
        row.provenance = {**row.provenance,"claims":claims}
        assert "normalized_description" in admission_error(db,row)


def test_duplicate_alias_evidence_collapses_display_edge():
    with SessionLocal() as db:
        rows, aliases = _catalog(db,[{"code":"VAG-TEST-ALIAS-DEDUP","description":"Synthetic alias duplicate test."}],
            aliases=[("VAG-TEST-ALIAS-DEDUP","P0301","production")])
        original = db.get(DiagnosticDataset,rows[0].dataset_id)
        dataset = DiagnosticDataset(namespace_id=original.namespace_id,source_id=original.source_id,name="Second alias evidence",
            version="v2",adapter_type="structured_json",checksum=assertion_hash(str(uuid4())),status="active",legal_use_confirmed=True)
        db.add(dataset)
        db.flush()
        a = aliases[0]
        db.add(DiagnosticCodeAlias(source_identifier_id=a.source_identifier_id,target_identifier_id=a.target_identifier_id,
            dataset_id=dataset.id,relationship_type=a.relationship_type,source_id=a.source_id,source_version=a.source_version,
            provenance=a.provenance,verification_status="verified",promotion_stage="production",is_generated=False))
        db.commit()
        result = DiagnosticDataResolver().resolve(db,"vag_uds","VAG-TEST-ALIAS-DEDUP")
        assert len(result["aliases"]) == 1 and len(result["aliases"][0]["evidence"]) == 2
        summary = coverage_report(db)["summary"]
        assert summary["distinct_alias_edges"] == 1 and summary["production_alias_evidence_rows"] == 2


def test_mislabeled_manufacturer_generic_rows_are_unavailable_and_seed_cleans_stale_database():
    with SessionLocal() as db:
        row = DiagnosticTroubleCode(code="B2100",category="body",generic_description="Synthetic stale generic-label regression.",
            manufacturer_specific=False,affected_system="unspecified",severity_hint="unknown",source_id=CATALOG_SOURCE_ID,
            confidence_tier="generic_standard",definition_type="generic_standardized")
        db.add(row)
        db.commit()
        assert resolve_dtc(db,"B2100").documented is False
        import_dtc_catalog(db)
        db.commit()
        db.refresh(row)
        assert row.generic_description == "" and row.source_id is None and row.confidence_tier == "quarantined"
        assert all(not resolve_dtc(db,code).documented for code in ("B2100","U2001","C2001","P1351"))


def test_revoking_source_withdraws_its_proof_and_is_audited(client):
    with SessionLocal() as db:
        _catalog(db,[{"code":"VAG-TEST-SOURCE-REVOCATION","description":"Synthetic source withdrawal fixture."}])
    response = client.post(f"/api/diagnostic-data/sources/{TEST_SOURCE_ID}/revoke",json={"reason":"Synthetic rights withdrawal audit test"})
    assert response.status_code == 200 and response.json()["revoked_at"]
    with SessionLocal() as db:
        assert DiagnosticDataResolver().resolve(db,"vag_uds","VAG-TEST-SOURCE-REVOCATION")["documented"] is False
        assert coverage_report(db)["summary"]["production_definition_rows"] == 0
