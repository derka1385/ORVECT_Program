from abc import ABC, abstractmethod
from app.schemas import AIAnalysisOutput

class LLMProvider(ABC):
    @abstractmethod
    def synthesize(self, context: dict) -> AIAnalysisOutput: ...

class MockLLMProvider(LLMProvider):
    def synthesize(self, context: dict) -> AIAnalysisOutput:
        step=context.get("step")
        return AIAnalysisOutput.model_validate({
            "summary":context.get("summary","Synthèse déterministe des informations disponibles. Aucun diagnostic de pièce n’est affirmé depuis le DTC seul."),
            "affected_systems":context.get("affected_systems",[{"name":"undetermined","reason":"Le système doit être confirmé par une documentation autorisée."}]),
            "hypotheses":[{"hypothesis_id":h["id"],"title":h["title"],"suspected_component":h["suspected_component"],"ranking_score":h["probability_score"],"confidence_label":h["confidence_label"],"supporting_evidence":h["supporting_evidence"],"contradicting_evidence":h["contradicting_evidence"],"source_ids":h["source_ids"],"source_references":h.get("source_references",[]),"verification_status":h.get("verification_status","unverified")} for h in context.get("hypotheses",[])],
            "recommended_next_step":step,
            "conclusion_status":context.get("conclusion_status","testing_required"),
            "limitations":context.get("limitations",["Corpus fictif réservé à la démonstration.","Le score est un classement interne, pas une probabilité scientifique.","Le jugement du professionnel reste indispensable."])
        })
