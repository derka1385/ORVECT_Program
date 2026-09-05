"""Remove inferred/manufacturer-ambiguous DTC rows from the active catalog.

The output intentionally contains only exact rows marked generic_standard in the
source dataset. Manufacturer-specific and family-inferred rows are not copied.
"""
import argparse
import hashlib
import json
import gzip
from pathlib import Path


def manufacturer_range(code):
    return code[1] == "1" or (code[0] in "BCU" and code[1] == "2")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=Path("data/fixtures/dtc_catalog.json"))
    parser.add_argument("--check", action="store_true", help="Validate the active catalog without rewriting it")
    parser.add_argument("--quarantine-output", type=Path, help="Preserve newly rejected active rows outside runtime")
    args = parser.parse_args()
    payload = json.loads(args.path.read_text())
    original = payload.get("definitions", [])
    definitions = []
    rejected = []
    for item in original:
        if item.get("confidence_tier") != "generic_standard" or item.get("manufacturer_specific") or manufacturer_range(item["code"]):
            rejected.append(item)
            continue
        description = item.get("description_en")
        if not description:
            continue
        definitions.append(
            {
                "code": item["code"],
                "category": item["category"],
                "is_generic": True,
                "manufacturer_specific": False,
                "confidence_tier": "generic_standard",
                "description_en": description,
            }
        )
    if args.check:
        report = payload.get("input_report", {})
        if len(definitions) != len(original):
            raise SystemExit("Unsafe, manufacturer-specific or empty DTC definitions remain active")
        if any(item["code"].upper() == "P1351" for item in definitions):
            raise SystemExit("P1351 must not have an unsourced active definition")
        if report.get("active_generic_definitions") != len(definitions):
            raise SystemExit("Catalog report does not match the active definition count")
        print(json.dumps(report, ensure_ascii=False))
        return
    prior_report = payload.get("input_report", {})
    if rejected:
        if not args.quarantine_output:
            raise SystemExit("Provide --quarantine-output to preserve rejected active rows")
        entries = [{**item, "promotion_stage": "quarantined", "quarantine_reason": "generic_label_conflicts_with_manufacturer_range"} for item in rejected]
        archive = {"schema_version": "1.0", "entry_count": len(entries), "entries": entries,
            "origin": "Phase 1.6 audit of the active Phase 1 generic fixture",
            "runtime_policy": "NEVER_LOADED_BY_PRODUCTION_RESOLVER",
            "entries_checksum_sha256": hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()}
        encoded = gzip.compress(json.dumps(archive, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0)
        if args.quarantine_output.exists() and args.quarantine_output.read_bytes() != encoded:
            raise SystemExit("Refusing to overwrite a different quarantine archive")
        args.quarantine_output.parent.mkdir(parents=True, exist_ok=True)
        args.quarantine_output.write_bytes(encoded)
    original_count = prior_report.get("original_rows", len(original))
    clean = {
        "schema_version": "1.0",
        "source": {
            "title": "DiagPilot active generic DTC catalog",
            "publisher": "Wal33D dataset, filtered by DiagPilot",
            "source_type": "open_source_dataset",
            "source_url": payload["source"]["source_url"],
            "source_commit": payload["source"]["source_commit"],
            "license_type": "MIT",
            "language": "en",
            "trust_level": "community_open_data",
            "review_status": "unreviewed",
            "standard_claim": "Rows are labeled generic by the source dataset but are not independently verified against the licensed current SAE J2012-DA.",
        },
        "input_report": {
            "original_rows": original_count,
            "active_generic_definitions": len(definitions),
            "unverified_or_manufacturer_rows_removed": original_count - len(definitions),
            "phase_1_6_additional_quarantined": prior_report.get("phase_1_6_additional_quarantined", 0) + len(rejected),
        },
        "definitions": definitions,
    }
    canonical = json.dumps(clean, ensure_ascii=False, sort_keys=True).encode()
    clean["content_checksum_sha256"] = hashlib.sha256(canonical).hexdigest()
    temporary = args.path.with_suffix(args.path.suffix + ".tmp")
    temporary.write_text(json.dumps(clean, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(args.path)
    print(json.dumps(clean["input_report"], ensure_ascii=False))


if __name__ == "__main__":
    main()
