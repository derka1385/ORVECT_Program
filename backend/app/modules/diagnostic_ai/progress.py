"""Real diagnostic stage reporting.

The technician UI polls these stages while the analysis runs, so the progress
shown is the pipeline's actual position — never a timed animation.

ponytail: process-local store; move to Redis if the API is ever run multi-worker.
"""

from dataclasses import dataclass, field
from time import monotonic

# Ordered pipeline stages. `label` is what the workshop sees.
STAGES = (
    ("context", "Lecture du contexte véhicule"),
    ("codes", "Interprétation des codes défaut"),
    ("knowledge", "Consultation de la base Orvect"),
    ("research_decision", "Évaluation du besoin de recherche externe"),
    ("research", "Recherche de preuves techniques externes"),
    ("reasoning", "Classement des hypothèses de cause racine"),
    ("test_plan", "Construction du plan de contrôle"),
    ("complete", "Diagnostic prêt"),
)
STAGE_LABELS = dict(STAGES)
STAGE_ORDER = [key for key, _ in STAGES]


@dataclass
class Progress:
    stage: str = "context"
    detail: str = ""
    started: float = field(default_factory=monotonic)
    failed: bool = False

    def as_dict(self) -> dict:
        return {
            "stage": self.stage,
            "label": STAGE_LABELS.get(self.stage, self.stage),
            "detail": self.detail,
            "index": STAGE_ORDER.index(self.stage) if self.stage in STAGE_ORDER else 0,
            "total": len(STAGE_ORDER),
            "elapsedMs": int((monotonic() - self.started) * 1000),
            "failed": self.failed,
            "stages": [{"key": key, "label": label} for key, label in STAGES],
        }


_active: dict[str, Progress] = {}


def start(case_id: str) -> None:
    _active[case_id] = Progress()


def set_stage(case_id: str, stage: str, detail: str = "") -> None:
    current = _active.get(case_id)
    if current:
        current.stage = stage
        current.detail = detail


def fail(case_id: str, detail: str) -> None:
    current = _active.get(case_id)
    if current:
        current.failed = True
        current.detail = detail


def finish(case_id: str) -> None:
    set_stage(case_id, "complete")


def read(case_id: str) -> dict | None:
    current = _active.get(case_id)
    return current.as_dict() if current else None


def clear(case_id: str) -> None:
    _active.pop(case_id, None)
