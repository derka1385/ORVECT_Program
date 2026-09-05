#!/usr/bin/env python3
"""Deterministic inventory only. Never restores or promotes archived content."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re

VAG_BRANDS = {"volkswagen", "vw", "audi", "skoda", "škoda", "seat", "cupra", "vag"}
CATEGORIES = ("obviously_generated", "generic_sae_candidate", "vag_numeric_candidate", "vag_pbcu_candidate",
              "other_oem_candidate", "malformed", "duplicate_alias_candidate", "unknown")


def is_generated(entry):
    return entry.get("confidence_tier") == "approximation_family" or "chatgpt" in (entry.get("approximation_method") or "").casefold()


def classify(entry):
    code = str(entry.get("code", "")).strip().upper()
    if not re.fullmatch(r"(?:[PBCU][0-9A-F]{4}|\d{5,6})", code):
        return "malformed"
    if is_generated(entry):
        return "obviously_generated"
    vag = str(entry.get("brand_hint", "")).casefold() in VAG_BRANDS
    if code.isdigit():
        return "vag_numeric_candidate" if vag else "unknown"
    if vag:
        return "vag_pbcu_candidate"
    if entry.get("is_generic") and not entry.get("manufacturer_specific"):
        return "generic_sae_candidate"
    if entry.get("brand_hint") and entry["brand_hint"] != "À identifier":
        return "other_oem_candidate"
    return "unknown"


def match_quarantine(entry, source_records):
    """Identifier-only leads cannot establish semantics, rights or aliases."""
    return [{"source_id": row["source_id"], "source_version": row["source_version"],
             "record_id": row["record_id"], "match_kind": "identifier_only",
             "automatically_promotable": False, "archive_remains_quarantined": True,
             "generated_archive_record_permanently_blocked": is_generated(entry)}
            for row in source_records if row.get("code") == entry.get("code")]


def analyze(path):
    blob = path.read_bytes()
    archive = json.loads(gzip.decompress(blob))
    entries = archive["entries"]
    canonical = json.dumps(entries, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    if hashlib.sha256(canonical).hexdigest() != archive["entries_checksum_sha256"] or len(entries) != archive["entry_count"]:
        raise ValueError("Quarantine checksum/count mismatch")
    categories = dict.fromkeys(CATEGORIES, 0)
    for entry in entries:
        categories[classify(entry)] += 1
    codes = Counter(entry["code"] for entry in entries)
    return {"schema_version": "1.0", "archive_sha256": hashlib.sha256(blob).hexdigest(),
        "entries_sha256": archive["entries_checksum_sha256"], "total": len(entries),
        "exclusive_categories": categories,
        "confidence_tiers": dict(sorted(Counter(x.get("confidence_tier", "unknown") for x in entries).items())),
        "shape_counts": {"pbcu": sum(bool(re.fullmatch(r"[PBCU][0-9A-F]{4}", x["code"])) for x in entries),
            "numeric": sum(x["code"].isdigit() for x in entries)},
        "nonempty_descriptions": sum(bool(x.get("description_en")) for x in entries),
        "unique_code_values": len(codes), "duplicate_code_rows": sum(n-1 for n in codes.values()),
        "explicit_vag_brand_hints": sum(str(x.get("brand_hint", "")).casefold() in VAG_BRANDS for x in entries),
        "unattributed_manufacturer_candidates": sum(x.get("confidence_tier") == "manufacturer_indicative" for x in entries),
        "independently_rights_cleared_vag_matching_sources": 0,
        "promoted": 0, "restored": 0,
        "limitations": ["Generic/brand flags are historical claims, not validation.",
            "P/B/C/U syntax does not identify a VAG manufacturer; no numeric VAG catalogue was found in this archive.",
            "No source with independently established reusable VAG semantics was acquired; semantic matching is not claimed.",
            "Duplicate wording is not alias evidence. Generated records remain permanently blocked even when a code is independently documented."]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=Path("quarantine/dtc_catalog_legacy_quarantine.json.gz"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(analyze(args.archive), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    print(result)


if __name__ == "__main__":
    main()
