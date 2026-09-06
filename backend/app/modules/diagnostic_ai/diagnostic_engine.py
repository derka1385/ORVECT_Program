from dataclasses import asdict,dataclass


@dataclass(frozen=True)
class DiagnosticGate:
    hypotheses_allowed: bool
    required_status: str | None
    reasons: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


class DiagnosticEngine:
    """Deterministic evidence gate; it never calls or interprets an LLM."""

    def evaluate(self,context:dict) -> DiagnosticGate:
        vehicle=context.get("vehicle",{})
        definitions=context.get("technical_definitions",[])
        fault_codes=context.get("fault_codes",[])
        if any(item.get("technician_verification", "confirmed") != "confirmed" for item in fault_codes):
            reasons=["dtc_interpretation_mismatch" if item.get("technician_verification")=="interpretation_mismatch" else "dtc_confirmation_required" for item in fault_codes if item.get("technician_verification", "confirmed") != "confirmed"]
            return DiagnosticGate(False,"human_escalation_required",sorted(set(reasons)))
        if not vehicle.get("configuration_confirmed") or not vehicle.get("engine_code"):
            return DiagnosticGate(False,"vehicle_configuration_not_sufficiently_identified",["vehicle_configuration_incomplete"])
        if any(item.get("resolution_status") in {"ambiguous","insufficient_vehicle_configuration"} for item in definitions):
            missing=sorted({field for item in definitions for field in item.get("missing_information",[])})
            return DiagnosticGate(False,"vehicle_configuration_not_sufficiently_identified",["diagnostic_definition_ambiguous",*missing])
        if any(item.get("definition_type")=="manufacturer_specific" and not item.get("documented") for item in definitions):
            return DiagnosticGate(False,"manufacturer_specific_definition_unavailable",["manufacturer_definition_unavailable"])
        if any(item.get("definition_type")=="unknown" or not item.get("documented") for item in definitions):
            return DiagnosticGate(False,"human_escalation_required",["dtc_definition_unknown"])
        informative_step=any(
            item.get("diagnostic_effect")=="informative" and (item.get("result") or {}).get("state") in {"positive","negative"}
            for item in context.get("previous_steps",[])
        )
        freeze_frame=any(bool(item.get("freeze_frame")) for item in context.get("fault_codes",[]))
        reported_symptoms=bool(str(context.get("untrusted_user_data",{}).get("symptoms") or "").strip())
        visual_evidence=bool(context.get("images"))
        if not (context.get("measurements") or informative_step or freeze_frame or reported_symptoms or visual_evidence):
            return DiagnosticGate(False,"insufficient_evidence",["dtc_alone_is_not_diagnostic_evidence"])
        reasons=[]
        if reported_symptoms:reasons.append("reported_symptoms_available")
        if context.get("measurements"):reasons.append("structured_measurements_available")
        if freeze_frame:reasons.append("freeze_frame_available")
        if informative_step:reasons.append("informative_test_result_available")
        if visual_evidence:reasons.append("visual_evidence_available")
        return DiagnosticGate(True,None,reasons)
