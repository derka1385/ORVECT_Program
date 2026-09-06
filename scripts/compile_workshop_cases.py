#!/usr/bin/env python3
"""Compile les fichiers JSON du formulaire ORVECT en JSONL et CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def flatten(case: dict) -> dict:
    vehicle = case.get("vehicle", {})
    incident = case.get("incident", {})
    resolution = case.get("resolution", {})
    return {
        "case_id": case.get("caseId"),
        "submitted_at": case.get("submittedAt"),
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "year": vehicle.get("firstRegistrationYear"),
        "engine_code": vehicle.get("engineCode"),
        "gearbox_code": vehicle.get("gearboxCode"),
        "power": vehicle.get("power"),
        "power_unit": vehicle.get("powerUnit"),
        "mileage_km": vehicle.get("mileageKm"),
        "fuel": vehicle.get("fuel"),
        "gearbox_type": vehicle.get("gearboxType"),
        "dtc_codes": "|".join(item.get("code", "") for item in incident.get("dtcs", [])),
        "dtc_meanings": "|".join(item.get("meaning", "") for item in incident.get("dtcs", [])),
        "symptoms": incident.get("symptoms"),
        "conditions": incident.get("occurrenceConditions"),
        "diagnostic_steps": incident.get("diagnosticSteps"),
        "repair_action": resolution.get("repairAction"),
        "root_cause": resolution.get("rootCause"),
        "parts_replaced": resolution.get("partsReplaced"),
        "outcome": resolution.get("outcome"),
        "verification": resolution.get("verification"),
        "lesson_learned": resolution.get("lessonLearned"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="Dossier contenant les exports .json reçus")
    parser.add_argument("--output", type=Path, default=Path("orvect-workshop-cases"))
    args = parser.parse_args()

    cases = []
    for path in sorted(args.input_dir.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if case.get("schema") != "orvect.workshop_case" or case.get("schemaVersion") not in (1, 2):
            print(f"Ignoré (schéma incompatible) : {path.name}")
            continue
        cases.append(case)

    jsonl_path = args.output.with_suffix(".jsonl")
    csv_path = args.output.with_suffix(".csv")
    jsonl_path.write_text("".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases), encoding="utf-8")
    rows = [flatten(case) for case in cases]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flatten({}).keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(cases)} cas compilé(s) : {jsonl_path} et {csv_path}")


if __name__ == "__main__":
    main()
