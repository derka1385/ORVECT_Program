import pytest
from app.modules.diagnostic_ai.diagnostic_engine import DiagnosticEngine
from app.modules.diagnostic_ai.providers import _mock_analysis, _normalize_provider_payload
from app.modules.diagnostic_ai.analysis_service import _validate_dtc_interpretations
from app.modules.diagnostic_ai.schemas import LLMDiagnosticAnalysis


def context(exploratory=True, code='P1351'):
    return {'exploration_mode':exploratory,
        'vehicle':{'configuration_confirmed':True,'engine_code':'CZCA'},
        'fault_codes':[{'namespace':'vag_obd','code':code,'ecu':'ECU moteur','technician_verification':'confirmed'}],
        'technical_definitions':[{'namespace':'vag_obd','code':code,'ecu':'ECU moteur','documented':False,'definition_type':'manufacturer_specific','description':'Definition unavailable for this vehicle configuration.','source':None,'resolution_status':'unknown'}],
        'untrusted_user_data':{'symptoms':'Ralenti irrégulier'},'measurements':[]}


def test_exploration_can_reason_without_catalogue_but_strict_mode_still_stops():
    assert DiagnosticEngine().evaluate(context()).hypotheses_allowed
    strict=DiagnosticEngine().evaluate(context(False))
    assert not strict.hypotheses_allowed
    assert strict.required_status=='manufacturer_specific_definition_unavailable'


@pytest.mark.parametrize('change', ['unconfirmed','mismatch','vehicle','code_only'])
def test_exploration_preserves_evidence_and_confirmation_gates(change):
    data=context()
    if change in ('unconfirmed','mismatch'):
        data['fault_codes'][0]['technician_verification']='unconfirmed' if change=='unconfirmed' else 'interpretation_mismatch'
    if change=='vehicle':data['vehicle']['configuration_confirmed']=False
    if change=='code_only':data['untrusted_user_data']['symptoms']=''
    assert not DiagnosticEngine().evaluate(data).hypotheses_allowed


def test_tentative_meaning_is_preserved_only_in_exploration_and_never_claims_a_source():
    data=context()
    payload=_mock_analysis(data).model_dump(mode='json')
    payload['interpretedFaultCodes'][0].update(meaning='Une anomalie de commande pourrait être en cause ; interprétation à vérifier.',sourceStatus='ai_general_knowledge_unverified',sources=[])
    normalized,_=_normalize_provider_payload(payload,data)
    analysis=LLMDiagnosticAnalysis.model_validate(normalized)
    _validate_dtc_interpretations(analysis,data)
    assert analysis.interpretedFaultCodes[0].meaning.startswith('Approximation Gemini non vérifiée : ')
    assert analysis.interpretedFaultCodes[0].sources==[]
    assert any('MODE EXPLORATOIRE' in warning for warning in analysis.warnings)
    strict,_=_normalize_provider_payload(payload,context(False))
    assert strict['interpretedFaultCodes'][0]['sourceStatus']=='not_found'
    assert strict['interpretedFaultCodes'][0]['meaning']=='Definition unavailable for this vehicle configuration.'


def test_documented_definition_cannot_be_overwritten_in_exploration():
    data=context()
    source={'source_id':'catalogue','source_type':'dataset','source_version':'1','vehicle_compatibility':{},'timestamp':'2026-09-08','verified':False}
    data['technical_definitions'][0].update(documented=True,description='Exact catalogue definition',source=source,resolution_status='resolved')
    payload=_mock_analysis(data).model_dump(mode='json')
    payload['interpretedFaultCodes'][0].update(meaning='Unsupported model guess',sourceStatus='ai_general_knowledge_unverified',sources=[])
    normalized,_=_normalize_provider_payload(payload,data)
    analysis=LLMDiagnosticAnalysis.model_validate(normalized)
    _validate_dtc_interpretations(analysis,data)
    assert analysis.interpretedFaultCodes[0].meaning=='Exact catalogue definition'
    assert analysis.interpretedFaultCodes[0].sourceStatus=='provided_by_database'


def test_prompt_version_fits_persisted_database_column():
    from app.database.models import AICall, DiagnosticSession
    from app.modules.diagnostic_ai.providers import PROMPT_VERSION
    for model in (AICall, DiagnosticSession):
        assert len(PROMPT_VERSION) <= model.__table__.c.prompt_version.type.length
