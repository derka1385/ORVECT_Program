"""Homologated generations / engine variants, and problems already reported on them.

Data comes from `data/vehicle_knowledge/` (built by donnees-pieces/connaissance):
- generations.json : Swiss type approvals (ASTRA open data) split into real generations,
  with every homologated engine variant;
- reported_issues.json : real-world problems — official recalls (NHTSA, RappelConso, EU Safety
  Gate), US manufacturer service bulletins (NHTSA), owner complaints aggregated per generation
  (NHTSA, counts only), and web research (press, specialist sites, forums), each with its sources.

Reported issues are external reports: they help rank hypotheses and choose checks, they are
never proof for a given vehicle (`verified=False`, separate trust class).
"""
import hashlib
import json
import math
import re
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models import EngineVariant, KnowledgeSource, ReportedIssueGeneration, ReportedVehicleIssue, VehicleGeneration
from app.modules.experience import trust

FIXTURE_SOURCE_ID = "vehicle-knowledge-fixture"
SCOPE = "reported_issue_unverified"
MAKE_ALIASES = {"VOLKSWAGEN": "VW", "ŠKODA": "SKODA", "CITROËN": "CITROEN", "MERCEDES": "MERCEDES-BENZ",
                "MERCEDES BENZ": "MERCEDES-BENZ", "VAUXHALL": "OPEL", "BMW MINI": "MINI"}
# Origin / evidence -> source type of the existing trust taxonomy. Web research stays a web
# field signal whatever it reports on: the summary is ours, not the manufacturer's document.
SOURCE_TYPE = {"nhtsa_recall": "safety_authority", "rappelconso": "safety_authority", "safety_gate": "safety_authority",
               "nhtsa_tsb": "oem_manufacturer", "web_research": "specialist_community",
               "nhtsa_complaints": "specialist_community"}  # plaintes : signal de terrain, pas une autorité
EVIDENCE_WEIGHT = {"official_recall": 3.0, "service_bulletin": 2.5, "press_investigation": 2.0,
                   "specialist_site": 1.5, "forum_reports": 1.0, "owner_complaints": 0.8}
DTC = re.compile(r"\b[PBCU][0-9A-F]{4}\b")
WORD = re.compile(r"[a-zà-ÿ0-9]{4,}")


def _data_dir() -> Path:
    for base in (Path.cwd(), Path(__file__).resolve().parents[4]):
        if (base / "data/vehicle_knowledge/generations.json").exists():
            return base / "data/vehicle_knowledge"
    return Path.cwd() / "data/vehicle_knowledge"


def normalize_make(make: str | None) -> str:
    value = re.sub(r"\s+", " ", (make or "").strip().upper())
    return MAKE_ALIASES.get(value, value)


def engine_tokens(code: str | None) -> list[str]:
    """'EB2ADT / HN05' -> ['EB2ADT', 'HN05'] ; 'K9KU8??' -> ['K9KU8']."""
    return [t.replace("?", "") for t in re.split(r"[\s/,;]+", (code or "").upper()) if t.replace("?", "")]


def codes_match(given: list[str], homologated: list[str]) -> bool:
    """« CZCA » (code complet fournisseur) = « CZC » (code frappé homologué) ; au moins 3 caractères communs."""
    return any(a == b or (min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a)))
               for a in given for b in homologated)


# ------------------------------------------------------------------ chargement
def load_reference_data(db: Session) -> bool:
    """(Re)load the fixtures when their checksum changed. Returns True when data was loaded."""
    folder = _data_dir()
    files = [folder / "generations.json", folder / "reported_issues.json"]
    if not all(f.exists() for f in files):
        return False
    digest = hashlib.sha256(b"".join(f.read_bytes() for f in files)).hexdigest()
    marker = db.get(KnowledgeSource, FIXTURE_SOURCE_ID)
    if marker and marker.checksum == digest and db.scalar(select(VehicleGeneration.id).limit(1)):
        return False
    generations = json.loads(files[0].read_text(encoding="utf-8"))
    issues = json.loads(files[1].read_text(encoding="utf-8"))
    db.execute(delete(ReportedIssueGeneration))
    db.execute(delete(EngineVariant))
    db.execute(delete(ReportedVehicleIssue))
    db.execute(delete(VehicleGeneration))
    for g in generations:
        years, core = g.get("years") or [None, None], g.get("years_core") or [None, None]
        db.add(VehicleGeneration(
            id=g["id"], make=g["make"], family=g["family"], label=g["label"], generation_code=g["generation_code"],
            type_code=g["type_code"], vin_code=g.get("vin_code") or None, year_from=years[0], year_to=years[1],
            core_year_from=core[0], core_year_to=core[1], fleet_reference=g.get("fleet_ch") or 0,
            vin_prefixes=g.get("vin_prefixes", []),
            specs={k: g.get(k) for k in ("names", "body", "dims_mm", "tyres", "brakes", "suspension", "steering",
                                          "final_drives", "emission_codes", "idle_rpm", "plate_location",
                                          "vin_location", "homologated_parts", "approvals_sample")}))
        seen = set()
        for e in g.get("engines", []):  # triés par parc décroissant : on garde la variante la plus répandue
            if e["code"][:60] in seen:
                continue
            seen.add(e["code"][:60])
            kw = e.get("kw") or [None, None]
            db.add(EngineVariant(
                generation_id=g["id"], engine_code=e["code"][:60], engine_types=e.get("types", []), fuel=e.get("fuel"),
                displacement_cc=e.get("cc"), power_kw_min=kw[0], power_kw_max=kw[1], torque_nm=e.get("nm"),
                cylinders=e.get("cylinders"), layout=e.get("layout_fr") or e.get("layout"), drive=e.get("drive", []),
                gearboxes=e.get("gearboxes", []), code_location=(e.get("code_location") or "")[:200] or None,
                example_name=(e.get("example") or "")[:120] or None, fleet_reference=e.get("parc") or 0))
    for i in issues:
        db.add(ReportedVehicleIssue(
            id=i["id"][:80], origin=i["origin"], market=i.get("market", "EU"), title=i["title"][:300],
            family=i.get("family", "")[:200], scope=i.get("match") or i.get("scope") or {}, generation_ids=i.get("generation_ids", []),
            system=i.get("system", "")[:120], component=i.get("component", "")[:200],
            failure_mode=i.get("failure_mode", "")[:120], symptoms=i.get("symptoms", []), dtc_codes=i.get("dtc_codes", []),
            cause=i.get("cause", ""), remedy=i.get("remedy", ""), checks=i.get("checks", []),
            applicability_note=i.get("applicability_note", ""), evidence_level=i["evidence_level"],
            source_type=SOURCE_TYPE.get(i["origin"], "general_web"), sources=i.get("sources", []),
            year_from=i.get("year_from"), year_to=i.get("year_to"), reported_at=i.get("reported_at"),
            review_state=i.get("review_state", "unreviewed")))
    db.flush()
    known = {g["id"] for g in generations}
    db.add_all(ReportedIssueGeneration(issue_id=i["id"][:80], generation_id=gid)
               for i in issues for gid in dict.fromkeys(i.get("generation_ids", [])) if gid in known)
    if not marker:
        marker = KnowledgeSource(id=FIXTURE_SOURCE_ID)
        db.add(marker)
    marker.title = "Générations, variantes moteur (ASTRA) et pannes signalées"
    marker.source_type = "orvect_catalog"
    marker.publisher = "ORVECT (compilation : ASTRA open data, NHTSA, RappelConso, recherche web)"
    marker.version = digest[:12]
    marker.license_type = "mixed: OGD-CH, public domain US, Licence Ouverte, web citations"
    marker.local_file_path = "data/vehicle_knowledge/"
    marker.checksum = digest
    marker.trust_level = "reference_data"
    marker.review_status = "unreviewed"
    db.flush()
    return True


# ------------------------------------------------------------------ identification
def _vin_matches(vin: str, prefix: str) -> bool:
    vin = vin[:11]
    return len(prefix) == 17 and len(vin) >= 9 and any(c != "." for c in prefix) and \
        all(p == "." or p == v for p, v in zip(prefix, vin))


def resolve(db: Session, make=None, model=None, model_year=None, engine_code=None, vin=None):
    """Best (generation, engine variant, basis) for an identified vehicle, or (None, None, [])."""
    mk = normalize_make(make)
    if not mk:
        return None, None, []
    vin = re.sub(r"[^A-Z0-9]", "", (vin or "").upper())
    mdl = (model or "").upper()
    tokens = engine_tokens(engine_code)
    best = (0, None, None, [])
    for gen in db.scalars(select(VehicleGeneration).where(VehicleGeneration.make == mk)):
        score, basis = 0, []
        if vin and any(_vin_matches(vin, p) for p in gen.vin_prefixes or []):
            score += 50
            basis.append("préfixe VIN homologué")
        if mdl and re.search(rf"(^|[^A-Z0-9]){re.escape(gen.family.upper())}([^A-Z0-9]|$)", mdl):
            score += 20
            basis.append("modèle")
        y0, y1 = gen.core_year_from or gen.year_from, gen.core_year_to or gen.year_to
        if model_year and y0 and y1:
            if y0 - 1 <= model_year <= y1 + 1:
                score += 15
                basis.append("années de production")
            else:
                score -= 30
        variant = None
        if tokens:
            for v in db.scalars(select(EngineVariant).where(EngineVariant.generation_id == gen.id)):
                if codes_match(tokens, engine_tokens(v.engine_code) + [t.upper() for t in v.engine_types or []]):
                    variant = v
                    break
            if variant:
                score += 25
                basis.append("code moteur homologué")
        if score > best[0] and score >= 35 and ("préfixe VIN homologué" in basis or "modèle" in basis):
            best = (score, gen, variant, basis)
    return best[1], best[2], best[3]


# ------------------------------------------------------------------ pannes signalées
def _fuel(value: str | None) -> str:
    v = (value or "").lower()
    if "diesel" in v or "gazole" in v:
        return "diesel"
    if "électrique" in v or "electric" in v:
        return "électrique"
    if "essence" in v or "gasoline" in v or "petrol" in v:
        return "essence"
    return v


def scope_matches(scope: dict, vehicle: dict, generation=None, variant=None) -> bool:
    """Every constraint present in `scope` must be satisfied by facts we actually know."""
    if not scope:
        return False
    if scope.get("makes") and normalize_make(vehicle.get("make")) not in scope["makes"]:
        return False
    tokens = engine_tokens(vehicle.get("engine_code")) + (engine_tokens(variant.engine_code) if variant else [])
    if scope.get("engine_code_regex"):
        if not tokens or not any(re.search(scope["engine_code_regex"], t, re.I) for t in tokens):
            return False
    if scope.get("engine_code_exclude_regex") and any(re.search(scope["engine_code_exclude_regex"], t, re.I) for t in tokens):
        return False
    if scope.get("fuel"):
        fuel = _fuel(variant.fuel if variant else vehicle.get("fuel_type"))
        if not fuel or not fuel.startswith(scope["fuel"]):
            return False
    cc = (variant.displacement_cc if variant else None) or vehicle.get("engine_displacement_cc")
    if (scope.get("min_cc") or scope.get("max_cc")) and not cc:
        return False
    if scope.get("min_cc") and cc < scope["min_cc"] or scope.get("max_cc") and cc > scope["max_cc"]:
        return False
    if scope.get("min_kw") and not (variant and (variant.power_kw_max or 0) >= scope["min_kw"]):
        return False
    if scope.get("gearbox_regex") and not (variant and any(re.search(scope["gearbox_regex"], g) for g in variant.gearboxes or [])):
        return False
    if scope.get("max_nm") and not (variant and variant.torque_nm and variant.torque_nm <= scope["max_nm"]):
        return False
    if scope.get("models"):
        text = f"{vehicle.get('model') or ''} {generation.family if generation else ''}".lower()
        if not any(m.lower() in text for m in scope["models"]):
            return False
    if scope.get("generations") and not (generation and generation.id in scope["generations"]):
        return False
    year = vehicle.get("model_year")
    if year and (scope.get("year_from") and year < scope["year_from"] or scope.get("year_to") and year > scope["year_to"]):
        return False
    return True


def find_issues(db: Session, vehicle: dict, generation=None, variant=None, dtc_codes=(), symptoms: str = "",
                limit: int = 8) -> list[dict]:
    """Reported issues compatible with the vehicle, most relevant first."""
    codes = {c.upper() for c in dtc_codes or []}
    words = set(WORD.findall((symptoms or "").lower()))
    year = vehicle.get("model_year")
    scored = []
    candidates = db.scalars(select(ReportedVehicleIssue).where(ReportedVehicleIssue.origin == "web_research")).all()
    if generation:
        official = db.scalars(select(ReportedVehicleIssue).join(
            ReportedIssueGeneration, ReportedIssueGeneration.issue_id == ReportedVehicleIssue.id).where(
            ReportedIssueGeneration.generation_id == generation.id)).all()
        candidates += [i for i in official
                       if not (year and i.year_from and i.year_to and not i.year_from - 1 <= year <= i.year_to + 1)]
    for issue in candidates:
        if issue.origin == "web_research" and not scope_matches(issue.scope, vehicle, generation, variant):
            continue
        dtc_hits = codes & set(issue.dtc_codes or [])
        text = " ".join([issue.title, issue.component, " ".join(issue.symptoms or [])]).lower()
        word_hits = words & set(WORD.findall(text))
        # Un code commun pèse d'autant plus que la panne cite peu de codes (spécificité).
        specificity = 1 / max(1, len(issue.dtc_codes or [])) ** 0.5
        score = EVIDENCE_WEIGHT.get(issue.evidence_level, 1.0) + 10 * len(dtc_hits) * specificity + 1.5 * min(len(word_hits), 6)
        if issue.origin == "web_research":
            score += 2  # ciblé sur le code moteur / la boîte : plus spécifique qu'un rappel de gamme
        if issue.origin == "nhtsa_tsb" and not (dtc_hits or word_hits):
            continue  # bulletin US sans lien avec le cas : bruit
        if issue.evidence_level == "official_recall" and not (dtc_hits or word_hits):
            score -= 2  # rappel sans rapport avec les symptômes : à signaler, pas à mettre en tête
        count = (issue.scope or {}).get("report_count") if issue.origin == "nhtsa_complaints" else None
        if count:
            if _fuel_conflict(issue.scope, vehicle, variant) or not (dtc_hits or word_hits or (count >= 50 and not (codes or words))):
                continue  # sans rapport avec les symptômes ; sans symptôme saisi, seuls les motifs massifs
            score += min(2.0, math.log10(count))  # 5 plaintes ≈ +0,7 ; 100 et plus = +2
        scored.append((score, issue, sorted(dtc_hits)))
    scored.sort(key=lambda s: -s[0])
    return [_as_dict(issue, hits) for _score, issue, hits in scored[:limit]]


def _fuel_conflict(scope: dict, vehicle: dict, variant) -> bool:
    """Motif de plaintes « diesel » sur un véhicule dont le carburant connu n'est pas diesel."""
    fuel = _fuel(variant.fuel if variant else vehicle.get("fuel_type"))
    return bool(scope.get("fuel") and fuel and not fuel.startswith(scope["fuel"]))


def _as_dict(issue: ReportedVehicleIssue, dtc_hits: list[str]) -> dict:
    return {"id": issue.id, "origin": issue.origin, "market": issue.market, "title": issue.title, "family": issue.family,
            "system": issue.system, "component": issue.component, "symptoms": issue.symptoms, "dtc_codes": issue.dtc_codes,
            "matched_dtc_codes": dtc_hits, "cause": issue.cause, "remedy": issue.remedy, "checks": issue.checks,
            "applicability_note": issue.applicability_note, "evidence_level": issue.evidence_level,
            "source_type": issue.source_type, "sources": issue.sources, "review_state": issue.review_state,
            "trust_class": trust.trust_class(issue.source_type)}


def as_excerpt(item: dict, generation_id: str | None) -> dict:
    """A reported issue as a citable technical excerpt (same shape as external research)."""
    first = (item["sources"] or [{}])[0]
    url = first.get("url")
    lines = [item["title"], f"Origine : {item['origin']} ({item['market']}), niveau : {item['evidence_level']}.",
             f"Symptômes signalés : {', '.join(item['symptoms'])}." if item["symptoms"] else "",
             f"Cause rapportée : {item['cause']}" if item["cause"] else "",
             f"Contrôles cités : {'; '.join(item['checks'])}." if item["checks"] else "",
             f"Codes cités : {', '.join(item['dtc_codes'])}." if item["dtc_codes"] else "",
             f"Applicabilité : {item['applicability_note']}" if item["applicability_note"] else ""]
    return {
        "id": "reported:" + item["id"],
        "title": item["title"],
        "excerpt": " ".join(x for x in lines if x)[:1200],
        "origin": "orvect_reported_issues",
        "trust_class": item["trust_class"],
        "vehicle_scope": {"scope": SCOPE, "generation": generation_id},
        "source": {
            "source_id": "reported:" + item["id"],
            "source_type": item["source_type"],
            "source_version": "2026-11",
            "vehicle_compatibility": {"scope": SCOPE, "generation": generation_id},
            "timestamp": "2026-11-18T00:00:00+00:00",
            "verified": False,
            "url": url,
            "title": first.get("publisher") or item["title"],
            "domain": re.sub(r"^https?://(www\.)?([^/]+).*$", r"\2", url) if url else None,
        },
    }


def vehicle_reference(generation, variant) -> dict | None:
    """Homologated facts the technician can check on the car (no inference)."""
    if not generation:
        return None
    s = generation.specs or {}
    ref = {"generation": generation.id, "label": f"{generation.label} ({generation.generation_code})",
           "years": [generation.core_year_from or generation.year_from, generation.core_year_to or generation.year_to],
           "source": generation.source, "idle_rpm_homologated": s.get("idle_rpm"), "emission_codes": s.get("emission_codes"),
           "brakes": s.get("brakes"), "plate_location": s.get("plate_location"), "vin_location": s.get("vin_location")}
    if variant:
        ref["engine_variant"] = {"engine_code": variant.engine_code, "types": variant.engine_types, "fuel": variant.fuel,
                                 "displacement_cc": variant.displacement_cc, "power_kw": [variant.power_kw_min, variant.power_kw_max],
                                 "torque_nm": variant.torque_nm, "layout": variant.layout, "gearboxes": variant.gearboxes,
                                 "engine_code_location": variant.code_location}
    return ref


def for_case(db: Session, vehicle: dict, dtc_codes, symptoms: str, vin: str | None = None) -> dict:
    """Context block for a diagnosis: homologated reference + reported issues as excerpts."""
    generation, variant, basis = resolve(db, vehicle.get("make"), vehicle.get("model"), vehicle.get("model_year"),
                                         vehicle.get("engine_code"), vin)
    issues = find_issues(db, vehicle, generation, variant, dtc_codes, symptoms)
    reference = vehicle_reference(generation, variant)
    if reference:
        reference["match_basis"] = basis
    return {"vehicle_reference": reference,
            "reported_issues": [as_excerpt(i, generation.id if generation else None) for i in issues]}
