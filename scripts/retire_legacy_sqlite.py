"""Archive an offline SQLite database without migrating or discarding any rows.

Stop every process using the file first. The destination must not already exist.
The original byte-for-byte file and an independently checked SQLite snapshot are
both retained. No table contents or personal data are printed in the report.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def inspect_database(connection):
    integrity = connection.execute("PRAGMA integrity_check").fetchall()
    if integrity != [("ok",)]:
        raise ValueError("SQLite integrity check failed; original retained")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("SQLite foreign key check failed; original retained")
    names = [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    return {name: connection.execute(
        'SELECT count(*) FROM "' + name.replace('"', '""') + '"'
    ).fetchone()[0] for name in names}


def retire(source: Path, destination: Path):
    source = source.resolve(strict=True)
    if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("SQLite sidecars present; stop writers and checkpoint before retirement")
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(destination, 0o700)
    original_hash = digest(source)
    snapshot = destination / "diagnostic.snapshot.db"
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        counts = inspect_database(original)
        with sqlite3.connect(snapshot) as backup:
            original.backup(backup)
            if inspect_database(backup) != counts:
                raise ValueError("Snapshot row counts do not match; original retained")
    os.chmod(snapshot, 0o600)
    if digest(source) != original_hash:
        raise ValueError("Source changed during backup; original retained")
    # rename, not deletion: preserve original bytes, including all legacy metadata.
    archived = destination / "diagnostic.original.db"
    source.rename(archived)
    os.chmod(archived, 0o600)
    manifest = {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "former_path": str(source), "original_path": str(archived),
        "snapshot_path": str(snapshot), "original_sha256": original_hash,
        "snapshot_sha256": digest(snapshot), "table_counts": counts,
        "integrity_check": "ok", "foreign_key_violations": 0,
        "disposition": "retired; all original data retained; no production import",
    }
    report = destination / "manifest.json"
    report.write_text(json.dumps(manifest, indent=2) + "\n")
    os.chmod(report, 0o600)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(retire(args.source, args.destination), indent=2))
