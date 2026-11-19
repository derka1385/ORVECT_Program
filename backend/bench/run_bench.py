#!/usr/bin/env python3
"""Banc d'essai d'Orvect engine : rejoue des dossiers à cause connue, étape par étape.

À chaque étape, le moteur ne reçoit que ce que le technicien savait à ce moment-là
(jamais le verdict). On mesure si la cause confirmée figure dans les 3 premières
hypothèses, son rang, si le premier contrôle proposé est celui qui départage, et ce
que l'analyse a coûté (durée, recherche web, jetons).

Usage (depuis backend/) :
    python -m bench.run_bench                 # fournisseur de .env (Nebius, Gemini…)
    python -m bench.run_bench --mock          # vérifie le banc sans appel payant
    python -m bench.run_bench --only n20      # un sous-ensemble de dossiers
Résultats : bench/results/<date>-<fournisseur>.json et un tableau dans le terminal.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def configure(mock: bool) -> None:
    """Base jetable et environnement isolé, posés avant tout import de l'application."""
    os.environ["DATABASE_URL"] = f"sqlite:///{HERE / '.bench.db'}"
    os.environ["APP_ENVIRONMENT"] = "test"  # pas de chargement automatique : on charge la référence nous-mêmes
    os.environ["AUTH_PROVIDER"] = "legacy"  # base jetable : le compte de démonstration local suffit, pas de Firebase
    os.environ.setdefault("DEMO_ADMIN_PASSWORD", "demo-change-me")
    os.environ.setdefault("DEMO_TECHNICIAN_PASSWORD", "demo-tech-change-me")
    if mock:
        os.environ["LLM_PROVIDER"] = "mock"
        os.environ["RESEARCH_ENABLED"] = "false"


def matches(patterns: list[str], text: str) -> bool:
    """Tous les motifs doivent apparaître (chaque motif peut contenir des alternatives)."""
    return all(re.search(p, text, re.I) for p in patterns)


def hypothesis_text(h: dict) -> str:
    return " ".join([h.get("label") or "", h.get("component") or ""] + (h.get("supportingEvidence") or []))


def check_text(c: dict) -> str:
    return " ".join([c.get("title") or "", c.get("objective") or ""] + (c.get("instructions") or []))


def score(analysis: dict, expected: dict) -> dict:
    hypotheses = sorted(analysis.get("hypotheses") or [], key=lambda h: -(h.get("confidence") or 0))
    rank = next((i + 1 for i, h in enumerate(hypotheses) if matches(expected["cause_patterns"], hypothesis_text(h))), None)
    checks = sorted(analysis.get("nextChecks") or [], key=lambda c: c.get("order") or 99)
    first = checks[0] if checks else {}
    return {
        "rank": rank, "top1": rank == 1, "top3": bool(rank and rank <= 3),
        "first_check_ok": bool(first) and matches(expected["check_patterns"], check_text(first)),
        "hypotheses": [h.get("label") for h in hypotheses[:4]],
        "first_check": first.get("title"),
        "conclusion": (analysis.get("finalConclusion") or {}).get("status"),
        "research": (analysis.get("researchMetadata") or {}).get("researchTriggered"),
        "safety": (analysis.get("safetyAssessment") or {}).get("status"),
    }


def run(cases: list[dict], client) -> list[dict]:
    from app.database.session import SessionLocal
    from app.database.models import AICall
    from app.modules.diagnostic_ai.routes import calls
    from sqlalchemy import select

    results = []
    for case in cases:
        case_id = None
        for index, stage in enumerate(case["stages"], 1):
            calls.clear()  # le banc enchaîne plus d'analyses que la limite par minute d'un garage
            body = {"vehicle": case["vehicle"], "symptoms": stage.get("symptoms", ""),
                    "circumstances": stage.get("circumstances", ""), "mileage": stage.get("mileage"),
                    "fault_codes": [{"code": c, "status": "active", "technician_verification": "confirmed"}
                                    for c in stage.get("fault_codes", [])],
                    "measurements": stage.get("measurements", [])}
            if case_id:
                body["case_id"] = case_id
            launched = client.post("/api/diagnostics/launch", json=body)
            if launched.status_code != 200:
                results.append({"case": case["id"], "stage": index, "error": f"launch {launched.status_code}: {launched.text[:200]}"})
                break
            case_id = launched.json()["case"]["id"]
            started = time.perf_counter()
            response = client.post(f"/api/diagnostics/{case_id}/analyze")
            seconds = round(time.perf_counter() - started, 1)
            row = {"case": case["id"], "trap": case.get("trap", False), "stage": index, "label": stage["label"], "seconds": seconds}
            if response.status_code != 200:
                row["error"] = f"analyze {response.status_code}: {response.text[:200]}"
            else:
                row.update(score(response.json(), case["expected"]))
                with SessionLocal() as db:
                    call = db.scalar(select(AICall).where(AICall.session_id == case_id, AICall.status == "completed")
                                     .order_by(AICall.created_at.desc()))
                    row["model"] = call.model if call else None
                    row["tokens"] = (call.token_usage or {}).get("total_tokens") if call else None
            results.append(row)
            print(f"  {case['id']:<26} étape {index} : rang {row.get('rank')} · 1er contrôle {'ok' if row.get('first_check_ok') else 'non'}"
                  f" · {seconds}s{' · ' + row['error'] if 'error' in row else ''}", flush=True)
    return results


def summary(results: list[dict]) -> str:
    lines = ["", "étape | dossiers | cause en 1er | cause dans le top 3 | 1er contrôle juste | recherche web | durée moy.",
             "---|---|---|---|---|---|---"]
    for stage in sorted({r["stage"] for r in results}):
        rows = [r for r in results if r["stage"] == stage and "error" not in r]
        if not rows:
            continue
        n = len(rows)
        pct = lambda k: f"{sum(1 for r in rows if r.get(k)) * 100 // n} %"
        lines.append(f"{stage} | {n} | {pct('top1')} | {pct('top3')} | {pct('first_check_ok')} | {pct('research')} | "
                     f"{sum(r['seconds'] for r in rows) / n:.0f} s")
    traps = [r for r in results if r.get("trap") and "error" not in r]
    if traps:
        lines.append(f"\nDossiers pièges (la panne connue du moteur n'est PAS la cause) : cause dans le top 3 "
                     f"{sum(1 for r in traps if r['top3'])}/{len(traps)} étapes.")
    errors = [r for r in results if "error" in r]
    if errors:
        lines.append(f"\n{len(errors)} étape(s) en erreur : " + "; ".join(f"{r['case']} ({r['error'][:80]})" for r in errors))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mock", action="store_true", help="fournisseur déterministe, sans appel payant")
    parser.add_argument("--only", default="", help="filtre sur l'identifiant des dossiers")
    parser.add_argument("--cases", default=str(HERE / "cases.json"))
    args = parser.parse_args()
    configure(args.mock)

    from fastapi.testclient import TestClient
    from app.core.config import settings
    from app.database.models import Base
    from app.database.session import SessionLocal, engine
    from app.main import app
    from app.modules.vehicle_knowledge import service as vehicle_knowledge
    from app.seed import seed

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
        vehicle_knowledge.load_reference_data(db)
        db.commit()
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"email": "admin@example.com", "password": os.environ["DEMO_ADMIN_PASSWORD"]}).status_code == 200

    cases = [c for c in json.loads(Path(args.cases).read_text()) if args.only in c["id"]]
    print(f"Banc Orvect : {len(cases)} dossier(s), fournisseur {settings.llm_provider}, recherche "
          f"{'active' if settings.research_enabled and settings.tavily_api_key else 'désactivée'}")
    results = run(cases, client)
    out = HERE / "results" / f"{datetime.now():%Y-%m-%d-%H%M}-{settings.llm_provider}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"provider": settings.llm_provider, "results": results}, ensure_ascii=False, indent=1))
    print(summary(results))
    print(f"\nDétail : {out}")


if __name__ == "__main__":
    sys.exit(main())
