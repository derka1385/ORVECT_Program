import importlib.util
from pathlib import Path
import sqlite3

import pytest


def load_retirement():
    script = Path(__file__).resolve().parents[3] / "scripts/retire_legacy_sqlite.py"
    spec = importlib.util.spec_from_file_location("retirement", script.resolve())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sqlite_retirement_preserves_original_bytes_and_all_rows(tmp_path):
    module = load_retirement()
    source = tmp_path / "legacy.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE dtcs (id INTEGER PRIMARY KEY, description TEXT)")
        db.executemany("INSERT INTO dtcs VALUES (?,?)", [(i, f"original {i}") for i in range(1234)])
    original_hash = module.digest(source)
    destination = tmp_path / "archive"
    report = module.retire(source, destination)
    assert not source.exists()
    assert module.digest(destination / "diagnostic.original.db") == original_hash
    assert report["table_counts"] == {"dtcs": 1234}
    with sqlite3.connect(destination / "diagnostic.snapshot.db") as backup:
        assert backup.execute("SELECT description FROM dtcs WHERE id=1233").fetchone()[0] == "original 1233"
    assert (destination.stat().st_mode & 0o777) == 0o700
    assert (destination / "diagnostic.original.db").stat().st_mode & 0o777 == 0o600


def test_sqlite_retirement_refuses_sidecars_and_existing_archive(tmp_path):
    module = load_retirement()
    source = tmp_path / "legacy.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE example (id INTEGER)")
    sidecar = tmp_path / "legacy.db-wal"
    sidecar.touch()
    with pytest.raises(ValueError, match="sidecars"):
        module.retire(source, tmp_path / "archive")
    sidecar.unlink()
    destination = tmp_path / "archive"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        module.retire(source, destination)
    assert source.exists()


@pytest.mark.parametrize("schema_version", ["1.0", "2.0"])
def test_legacy_or_invalid_analysis_is_retained_without_breaking_current_ui(client, schema_version):
    from app.database.models import AICall
    from app.database.session import SessionLocal
    from app.seed import VEHICLE_ID

    case = client.post("/api/diagnostics", json={"vehicle_id": VEHICLE_ID}).json()
    original = {"schemaVersion": "1.0", "urgency": {"level": "low"}, "caseSummary": "Historical output"}
    with SessionLocal() as db:
        call = AICall(session_id=case["id"], provider="mock", model="legacy",
                      schema_version=schema_version, prompt_version="old", request_id="legacy-test",
                      input_hash="0" * 64, output_payload=original, validation_status="valid", latency_ms=0)
        db.add(call)
        db.commit()
        call_id = call.id
    response = client.get(f"/api/diagnostics/{case['id']}")
    assert response.status_code == 200
    assert response.json()["analysis"] is None
    assert response.json()["analysis_status"] == "legacy_requires_review"
    with SessionLocal() as db:
        assert db.get(AICall, call_id).output_payload == original
