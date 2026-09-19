"""Evidence strength.

This is deliberately not an LLM self-assessment and not a calibrated
probability. It scores how well-evidenced the case is — how much vehicle
context, how specific the codes, how many independent good-quality sources
agree — and says plainly what would raise it. It is never "the probability the
repair will work"; the schema carries `metric = evidence_strength` and
`calibrated = False` so no client can read it as one.

A calibrated `diagnostic_confidence` becomes possible only once the Experience
Engine holds enough confirmed outcomes to fit one against observed reality.
Until then, fabricating a probability would be worse than having none.
"""

from .schemas import DiagnosticConfidence, LLMDiagnosticAnalysis

BASE_SCORE = 20


def _independent_domains(analysis: LLMDiagnosticAnalysis) -> set[str]:
    domains = set()
    for hypothesis in analysis.hypotheses:
        for source in hypothesis.sources:
            if source.domain:
                domains.add(source.domain)
    return domains


def _best_source_rank(analysis: LLMDiagnosticAnalysis) -> int:
    from app.modules.research.tavily import SOURCE_RANK

    ranks = [
        SOURCE_RANK.get(source.source_type, 0)
        for hypothesis in analysis.hypotheses
        for source in hypothesis.sources
    ]
    return max(ranks, default=0)


# ORVECT field evidence is scored on its own terms rather than folded into the
# external-source ranking: corroborated observation is useful, and it is still
# not manufacturer documentation. Keeping the two separate is what stops volume
# from silently buying authority.
FIELD_EVIDENCE_ESTABLISHED_BONUS = 12
FIELD_EVIDENCE_CORROBORATED_BONUS = 7
FIELD_EVIDENCE_CONTRADICTION_PENALTY = 10


def _field_evidence(context: dict) -> dict:
    return context.get("field_evidence_summary") or {}


def assess(analysis: LLMDiagnosticAnalysis, context: dict, research: dict) -> DiagnosticConfidence:
    vehicle = context.get("vehicle", {})
    factors: list[str] = []
    improved_by: list[str] = []
    score = BASE_SCORE

    if not analysis.hypotheses:
        return DiagnosticConfidence(
            score=0,
            label="low",
            factors=["Aucune hypothèse n’a pu être classée de façon défendable."],
            improvedBy=[
                "Confirmer la configuration exacte du véhicule",
                "Ajouter des mesures ou un freeze-frame",
                "Confirmer l’interprétation des codes défaut relevés",
            ],
            decisionSource="confidence_heuristic",
        )

    # Vehicle context: a diagnosis on a confirmed engine code is far more specific.
    if vehicle.get("engine_code"):
        score += 12
        factors.append("Motorisation identifiée et confirmée")
    else:
        improved_by.append("Confirmer le code moteur exact")
    if vehicle.get("model_year") and vehicle.get("make") and vehicle.get("model"):
        score += 6
        factors.append("Identité véhicule complète")

    # DTC specificity: a documented definition beats an unavailable one.
    documented = [item for item in context.get("technical_definitions", []) if item.get("documented")]
    if documented:
        score += 10
        factors.append(f"{len(documented)} définition(s) DTC documentée(s) en catalogue")
    if any(not item.get("documented") for item in context.get("technical_definitions", [])):
        improved_by.append("Obtenir une définition constructeur exacte pour les codes non documentés")

    # Independent supporting sources and their quality.
    domains = _independent_domains(analysis)
    if len(domains) >= 3:
        score += 16
        factors.append(f"{len(domains)} sources externes indépendantes convergentes")
    elif len(domains) == 2:
        score += 10
        factors.append("2 sources externes indépendantes")
    elif len(domains) == 1:
        score += 5
        factors.append("1 source externe")
    else:
        improved_by.append("Aucune preuve externe rattachée aux hypothèses")

    best_rank = _best_source_rank(analysis)
    if best_rank >= 5:
        score += 12
        factors.append("Preuve de niveau constructeur ou autorité de sécurité")
    elif best_rank >= 3:
        score += 7
        factors.append("Documentation technique reconnue")
    elif best_rank > 0:
        factors.append("Preuves issues de communautés spécialisées uniquement")
        improved_by.append("Rechercher une documentation constructeur ou un bulletin technique")

    # Structured evidence actually collected in the workshop.
    if context.get("measurements"):
        score += 8
        factors.append("Mesures structurées disponibles")
    else:
        improved_by.append("Ajouter des mesures (carburant, compression, relevés électriques)")
    if any(item.get("freeze_frame") for item in context.get("fault_codes", [])):
        score += 8
        factors.append("Freeze-frame disponible")
    else:
        improved_by.append("Ajouter les données freeze-frame du code principal")
    if any(
        item.get("diagnostic_effect") == "informative" for item in context.get("previous_steps", [])
    ):
        score += 10
        factors.append("Résultat de contrôle informatif déjà enregistré")

    # Uncertainty and disagreement pull the score down.
    contradictions = sum(len(item.contradictingEvidence) for item in analysis.hypotheses)
    if contradictions:
        score -= min(12, 3 * contradictions)
        factors.append("Éléments contradictoires relevés entre les pistes")
    if all(item.verificationStatus == "unverified" for item in analysis.hypotheses):
        score -= 8
        factors.append("Toutes les hypothèses restent non vérifiées")
    if research.get("researchTriggered") and not research.get("externalResearchAvailable"):
        score -= 6
        factors.append("Vérification externe indisponible pour ce dossier")
    if len(analysis.hypotheses) >= 4:
        score -= 5
        factors.append("Plusieurs causes racines restent plausibles")

    # ORVECT's own accumulated experience.
    field = _field_evidence(context)
    if field.get("available"):
        support = field.get("strongest_support")
        garages = field.get("independent_garages", 0)
        confirmed = field.get("confirmed_cases", 0)
        if support == "established":
            score += FIELD_EVIDENCE_ESTABLISHED_BONUS
            factors.append(
                f"Expérience ORVECT établie : {confirmed} cas confirmés sur {garages} ateliers"
            )
        elif support == "corroborated":
            score += FIELD_EVIDENCE_CORROBORATED_BONUS
            factors.append(
                f"Expérience ORVECT corroborée : {confirmed} cas confirmés sur {garages} ateliers"
            )
        else:
            factors.append("Expérience ORVECT encore isolée sur ce cas")
            improved_by.append("Confirmer la cause racine et l’issue de la réparation")
        if field.get("contradicted"):
            score -= FIELD_EVIDENCE_CONTRADICTION_PENALTY
            factors.append("Des cas ORVECT contredisent cette cause racine")
        if field.get("distinct_root_causes", 0) > 1:
            factors.append("L’expérience ORVECT diverge sur la cause racine")
    else:
        improved_by.append("Accumuler des issues confirmées sur des véhicules compatibles")

    score = max(5, min(95, score))
    label = "strong" if score >= 75 else "good" if score >= 55 else "moderate" if score >= 35 else "low"
    return DiagnosticConfidence(
        score=score,
        label=label,
        factors=factors,
        improvedBy=list(dict.fromkeys(improved_by))[:5],
        decisionSource="confidence_heuristic",
    )
