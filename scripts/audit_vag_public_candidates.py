#!/usr/bin/env python3
"""Pinned public-file audit. Never imports, approves rights or stores diagnostic text.

Run from the repository root with backend/.venv/bin/python (PyYAML from test lock).
Only counts, source hashes and identifier-only quarantine leads are persisted.
No upstream program, SQL script or deserialization hook is executed.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
import zipfile

import yaml

CODE = re.compile(r"[PBCU][0-9A-F]{4}|[0-9]{5,6}")
COMPACT_SUBTYPE = re.compile(r"([PBCU][0-9A-F]{4})([0-9A-F]{2})")
ROOT = Path(__file__).resolve().parents[1]
SPECS = [
    ("riz4d/OpenVAG", "407d5e042cf46d55087ed4ae4e056605f2b04f08", "licence_uncertain",
     ["LICENSE", "README.md", "db/README.md", "db/schema.sql", ".gitignore"], []),
    ("foerbsnavi/OBDex", "bc58b0eb7273226a1aabae98e956b70b8362bda1", "rejected",
     ["LICENSE-CODE", "LICENSE-DATA", "CONTRIBUTING.md", "tools/_archive/README.md", "tools/_archive/add_wikipedia_sources.mjs"],
     [(f"data/generic/{family}xxx_enriched.yaml", "yaml", False) for family in ["B0", "C0", "P0", "P2", "P3", "U0", "U3"]]),
    ("vovakirdan/autosvc", "41638493c8aca4d0f3ef692c8a8b18e4b78915c9", "licence_uncertain",
     ["README.md", "pyproject.toml", "docs/manual/DTC.md"],
     [(f"autosvc/data/vag/dtc_{system}.json", "json", True) for system in ["body", "chassis", "network", "powertrain"]]),
    ("meatro/OpenHaldex-S3", "4fbdb170acc80712a7d8a67538b372cccdee8e86", "rejected",
     ["LICENSE", "data/LICENSE.md", "src/functions/diag/uds.cpp", "data/diag.html"], []),
    ("mytrile/obd-trouble-codes", "24e3ca8b9e66ab9c5e3d171bf8480e4509c38563", "licence_uncertain",
     ["LICENSE", "README.md"], [("obd-trouble-codes.json", "json", False)]),
    ("lennykean/OBDII.DTC", "bdd618ea487e9e85c7f3b4d142ce783337752f3b", "licence_uncertain",
     ["LICENSE", "README.md"], [("DTC.cs", "csharp", False)]),
    ("kierandrewett/obd", "b56a07a2ffc0d574e68e6426ff55418ee4173b7a", "licence_uncertain",
     ["LICENSE", "README.md", "scripts/fetch_dtc_codes.js"],
     [(f"dtc_codes/{brand}.json", "json", True) for brand in ["audi", "volkswagen"]]),
    ("bri3d/VW_Flash", "293f46d782bae2ced930497889b71eb782f122cb", "licence_uncertain",
     ["LICENSE", "lib/dtc_handler.py"], [("data/dtcs.csv", "csv", True)]),
    ("baconwaifu/PyVCDS", "45c95dc700a4aa2d46aefb6faf0a09bdb42d4a09", "rejected",
     ["README.md", "dtcs.py"], []),
]


def fetch(url, limit=15_000_000):
    with urlopen(Request(url, headers={"User-Agent": "DiagPilot-public-acquisition-audit/1.6"}), timeout=45) as response:
        blob = response.read(limit + 1)
    if len(blob) > limit:
        raise ValueError("Public audit file exceeds size limit")
    return blob


def normalized_records(blob, kind):
    """Extract actual identifiers, not arithmetic mappings or inferred definitions."""
    if kind == "csv":
        return list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))
    if kind == "csharp":
        return [{"code": code} for code in re.findall(r"^\s*([PBCU][0-9A-F]{4})\s*=", blob.decode(), re.M)]
    parsed = yaml.safe_load(blob) if kind == "yaml" else json.loads(blob)
    if isinstance(parsed, list):
        if not all(isinstance(row, dict) for row in parsed):
            raise ValueError("Unexpected list record schema")
        # mytrile JSON uses the first CSV row as column names; do not treat
        # that header as a diagnostic record or invent missing fields.
        if parsed and all("P0100" in row and len(row) == 2 for row in parsed):
            return [{"code": row["P0100"], "description": next(value for key, value in row.items() if key != "P0100")}
                    for row in parsed]
        return parsed
    if isinstance(parsed, dict) and all(CODE.fullmatch(str(key)) for key in parsed):
        return [{"code": code, "description": description} for code, description in parsed.items()]
    raise ValueError("Unknown dataset schema; cannot claim a record count")


def identifiers(records):
    values = set()
    for row in records:
        for field in ("code", "dtc", "dtc_code", "pcode"):
            value = str(row.get(field, "")).strip().upper()
            if CODE.fullmatch(value) or (field == "pcode" and COMPACT_SUBTYPE.fullmatch(value)):
                values.add(value)
    return values


def quarantine_leads(entries, codes):
    """No text comparison and NO promotion, even if a public identifier agrees."""
    matched = [row for row in entries if row.get("code") in codes]
    return {
        "identifier_only_matches": len(matched),
        "generated_matches_permanently_blocked": sum(
            row.get("confidence_tier") == "approximation_family"
            or "chatgpt" in str(row.get("approximation_method", "")).casefold()
            for row in matched
        ),
        "semantically_validated": 0, "promoted": 0,
        "reason": "Shared identifier is not evidence of semantics, VAG applicability, independent origin or reuse rights",
    }


def audit(spec, entries):
    repo, commit, classification, evidence_paths, datasets = spec
    result = {"source_id": repo, "source_url": f"https://github.com/{repo}",
              "source_version": commit, "classification": classification,
              "files": [], "errors": [], "imported": 0, "promoted": 0}
    all_codes, vag_codes, count = set(), set(), 0
    base = f"https://raw.githubusercontent.com/{repo}/{commit}/"
    for path, kind, vag in [(p, None, False) for p in evidence_paths] + datasets:
        try:
            blob = fetch(base + path)
            info = {"path": path, "url": base + path, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}
            if kind:
                records = normalized_records(blob, kind)
                codes = identifiers(records)
                count += len(records)
                all_codes.update(codes)
                if vag:
                    vag_codes.update(codes)
                origins = Counter(url for row in records for url in row.get("sources", []) if isinstance(url, str))
                info.update(record_count=len(records), identifier_count=len(codes),
                            compact_pbcu_subtype_representations=len({c for c in codes if COMPACT_SUBTYPE.fullmatch(c)}),
                            declared_vag_context=vag, record_fields=sorted({key for row in records for key in row}),
                            referenced_origins=dict(sorted(origins.items())))
            result["files"].append(info)
        except Exception as exc:
            result["errors"].append({"path": path, "error": f"{type(exc).__name__}: {exc}"})
    vag_pbcu_bases = {code[:5] if COMPACT_SUBTYPE.fullmatch(code) else code for code in vag_codes}
    result.update(inspected_record_rows=count, unique_identifiers=len(all_codes),
                  identifiers_in_vag_labelled_files=len(vag_codes),
                  manufacturer_range_identifiers_in_vag_files=sum(
                      bool(re.fullmatch(r"[PBCU][0-9A-F]{4}", code))
                      and (code[1] == "1" or (code[0] in "BCU" and code[1] == "2"))
                      for code in vag_pbcu_bases),
                  quarantine=quarantine_leads(entries, vag_codes | {
                      match.group(1) for code in vag_codes if (match := COMPACT_SUBTYPE.fullmatch(code))
                  }),
                  counting_note="Rows and identifiers are not deduplicated diagnostic concepts; a VAG-labelled file may contain generic codes.")
    return result


def external_audits():
    """Non-GitHub candidates, retaining neither complaint/VIN data nor text."""
    results = []

    def read(url, result):
        blob = fetch(url)
        result.setdefault("files", []).append({"url": url, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)})
        return blob

    for source in ["zenodo:15626055", "gitlab:mvglasow/open-kw1281", "hf:RRK1987/automotive-diagnostics-v2",
                   "kaggle:donnetew/odb2-powertrain-codes", "odxtools:somersault", "nhtsa:complaints-golf-2019"]:
        result = {"source_id": source, "files": [], "errors": [], "imported": 0, "promoted": 0}
        try:
            if source.startswith("zenodo"):
                meta = json.loads(read("https://zenodo.org/api/records/15626055", result))
                datafile = next(f for f in meta["files"] if f["key"].endswith(".json"))
                rows = json.loads(read(datafile["links"]["self"], result))
                result.update(classification="rejected", licence=meta["metadata"]["license"]["id"],
                              source_version=meta["metadata"]["doi"], inspected_record_rows=len(rows),
                              fields=sorted({k for row in rows for k in row}),
                              dtc_identifier_tokens=len(set(re.findall(r"\b[PBCU][0-9A-F]{4}\b", json.dumps(rows)))),
                              vag_definitions=0, reason="Fault/symptom cases without DTC identities or VAG applicability")
            elif source.startswith("gitlab"):
                url = "https://gitlab.com/api/v4/projects/mvglasow%2Fopen-kw1281"
                tree = json.loads(read(url + "/repository/tree?recursive=true&per_page=100", result))
                if len(tree) == 100:
                    raise ValueError("Pagination required before claiming complete tree")
                result.update(classification="rejected", tree_paths=[item["path"] for item in tree],
                              inspected_record_rows=0, vag_definitions=0, licence="not established",
                              reason="Repository contains README only; no diagnostic dataset")
            elif source.startswith("hf"):
                name = "RRK1987/automotive-diagnostics-v2"
                meta = json.loads(read("https://huggingface.co/api/datasets/" + name, result))
                size = json.loads(read("https://datasets-server.huggingface.co/size?dataset=" + name, result))
                rows = []
                for split in ["train", "validation"]:
                    view = json.loads(read("https://datasets-server.huggingface.co/rows?dataset=" + name
                                           + "&config=default&split=" + split + "&offset=0&length=100", result))
                    rows.extend(row["row"] for row in view["rows"])
                result.update(classification="rejected", licence=meta["cardData"]["license"], source_version=meta["sha"],
                              advertised_rows=size["size"]["dataset"]["num_rows"], inspected_record_rows=len(rows),
                              rows_mentioning_volkswagen=sum("volkswagen" in str(row.get("user", "")).casefold() for row in rows),
                              vag_definitions=0, reason="Generated training conversations, not attested ECU/code definitions; dataset-server snapshot is mutable")
            elif source.startswith("kaggle"):
                meta = json.loads(read("https://www.kaggle.com/api/v1/datasets/list?search=odb2-powertrain-codes", result))
                item = next(row for row in meta if row["ref"] == "donnetew/odb2-powertrain-codes")
                blob = read("https://www.kaggle.com/api/v1/datasets/download/donnetew/odb2-powertrain-codes", result)
                files = []
                with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                    if sum(m.file_size for m in archive.infolist()) > 15_000_000:
                        raise ValueError("Expanded research archive exceeds limit")
                    for member in archive.infolist():
                        if member.filename.endswith(".csv"):
                            content = archive.read(member)
                            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
                            files.append({"path": member.filename, "sha256": hashlib.sha256(content).hexdigest(),
                                          "rows": len(rows), "fields": sorted(rows[0]) if rows else []})
                result.update(classification="research_only", licence=item["licenseName"], source_version=item["lastUpdated"],
                              csv_files=files, inspected_record_rows=sum(f["rows"] for f in files),
                              reason="Non-commercial licence: not admitted for commercial diagnostic catalogue")
            elif source.startswith("odxtools"):
                version = "e0abc78e8714b6536fa0f59d3ad16081461e69e8"
                base = "https://raw.githubusercontent.com/mercedes-benz/odxtools/" + version + "/"
                read(base + "LICENSE", result)
                blob = read(base + "examples/somersault.pdx", result)
                with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                    if sum(m.file_size for m in archive.infolist()) > 15_000_000:
                        raise ValueError("Expanded research archive exceeds limit")
                    files = [{"path": member.filename, "bytes": member.file_size,
                              "dtc_elements": len(re.findall(rb"<DTC(?:\s|>)", archive.read(member)))}
                             for member in archive.infolist() if not member.is_dir()]
                result.update(classification="rejected", source_version=version, licence="MIT", archive_members=files,
                              vag_definitions=0, reason="Fictional somersault ECU; structural test corpus, not automotive VAG data")
            else:
                data = json.loads(read("https://api.nhtsa.gov/complaints/complaintsByVehicle?make=VOLKSWAGEN&model=GOLF&modelYear=2019", result))
                result.update(classification="research_only", source_version="live API snapshot", inspected_record_rows=len(data["results"]),
                              fields=sorted(data["results"][0]) if data["results"] else [],
                              dtc_identifier_tokens=len(set(re.findall(r"\b[PBCU][0-9A-F]{4}\b", json.dumps(data["results"])))),
                              vag_definitions=0, licence="Government API access is not a blanket OEM-text reuse licence",
                              reason="Owner complaints, not authoritative DTC mappings; personal content/VIN never persisted")
        except Exception as exc:
            result["errors"].append(f"{type(exc).__name__}: {exc}")
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive_blob = (ROOT / "quarantine/dtc_catalog_legacy_quarantine.json.gz").read_bytes()
    archive = json.loads(gzip.decompress(archive_blob))
    entries = archive["entries"]
    canonical = json.dumps(entries, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    if len(entries) != archive["entry_count"] or hashlib.sha256(canonical).hexdigest() != archive["entries_checksum_sha256"]:
        raise SystemExit("Archive integrity check failed")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda spec: audit(spec, entries), SPECS))
    external = external_audits()
    report = {"schema_version": "1.0", "retrieved_at": datetime.now(timezone.utc).isoformat(),
              "policy": "RESEARCH_METADATA_ONLY_NO_DIAGNOSTIC_TEXT_OR_RUNTIME_WRITES",
              "archive_sha256": hashlib.sha256(archive_blob).hexdigest(), "archive_entries": len(entries),
              "sources": results, "external_sources": external, "imported": 0, "quarantine_entries_validated": 0,
              "errors": sum(len(row["errors"]) for row in results + external)}
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized)
    print(json.dumps({"output": str(args.output), "errors": report["errors"],
                      "sources": [{k: row[k] for k in ("source_id", "inspected_record_rows", "unique_identifiers", "quarantine")} for row in results]}))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
