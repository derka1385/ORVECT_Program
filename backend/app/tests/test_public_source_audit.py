"""Audit mechanics only: authored examples are not real automotive definitions."""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


spec = importlib.util.spec_from_file_location(
    "public_source_audit", Path(__file__).resolve().parents[3] / "scripts/audit_vag_public_candidates.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_identifier_only_matches_never_validate_or_promote_generated_records():
    entries = [{"code": "P1999", "confidence_tier": "approximation_family"}, {"code": "P1998"}]
    before = json.dumps(entries)
    result = audit.quarantine_leads(entries, {"P1999", "P1998"})
    assert result["identifier_only_matches"] == 2
    assert result["generated_matches_permanently_blocked"] == 1
    assert result["semantically_validated"] == result["promoted"] == 0
    assert json.dumps(entries) == before


def test_audit_preserves_numeric_and_explicit_subtype_representations_without_conversion():
    rows = audit.normalized_records(b"code,pcode,name\n19999,P199900,Authored test label\n", "csv")
    assert audit.identifiers(rows) == {"19999", "P199900"}
    assert "P1999" not in audit.identifiers(rows)  # matching leads are a separate operation


def test_header_keyed_legacy_json_is_counted_without_turning_header_into_record():
    rows = audit.normalized_records(b'[{"P0100":"P1999","Legacy header":"Authored fixture"}]', "json")
    assert len(rows) == 1
    assert audit.identifiers(rows) == {"P1999"}


def test_unknown_schema_and_executable_yaml_are_rejected():
    with pytest.raises(ValueError, match="Unknown dataset schema"):
        audit.normalized_records(b'{"not_a_dtc":"text"}', "json")
    with pytest.raises(yaml.constructor.ConstructorError):
        audit.normalized_records(b'!!python/object/apply:builtins.str ["not executed"]', "yaml")
