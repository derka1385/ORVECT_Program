import hashlib, json, time, uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.logging import logger
from app.database.models import AICall, DiagnosticEvent, DiagnosticHypothesis, DiagnosticObservation, DiagnosticSession, DiagnosticStep, DiagnosticTroubleCode, KnowledgeSource, now
from app.modules.ai.provider import MockLLMProvider
from app.modules.dtc.service import resolve_dtc,source_reference
from app.modules.diagnostic_ai.schemas import NON_INFORMATIVE_RESULT_STATES
from app.schemas import AIAnalysisOutput, StepComplete

def event(db, session_id, kind, payload, actor_id=None):
    db.add(DiagnosticEvent(session_id=session_id,event_type=kind,payload=payload,actor_type="technician" if actor_id else "system",actor_id=actor_id))

def _source(db): return db.scalar(select(KnowledgeSource).where(KnowledgeSource.trust_level=="demo"))
def _hypothesis_data(source_id):
    return [
      dict(title="Bobine d’allumage cylindre 1 défaillante",component="ignition_coil_1",score=65,label="medium",reason="P0301 est compatible mais ne prouve pas la défaillance.",support=["Raté localisé cylindre 1"],against=[]),
      dict(title="Bougie cylindre 1 usée ou contaminée",component="spark_plug_1",score=55,label="medium",reason="Une bougie peut provoquer un raté localisé.",support=["Raté localisé cylindre 1"],against=[]),
      dict(title="Alimentation carburant cylindre 1 irrégulière",component="injector_1",score=35,label="low",reason="L’injecteur reste une hypothèse à tester après l’allumage.",support=["Combustion irrégulière"],against=["Aucune mesure carburant disponible"]),
      dict(title="Défaut mécanique ou étanchéité cylindre 1",component="cylinder_1",score=25,label="low",reason="À envisager si allumage et injection sont exclus.",support=["Raté persistant possible"],against=["Aucun test mécanique effectué"]),
    ]

def first_step(source_id,source_ref):
    return dict(title="Permuter les bobines des cylindres 1 et 2",objective="Vérifier si le raté suit la bobine sans conclure à partir du seul DTC.",instructions=["Couper le contact et laisser refroidir le moteur.","Identifier les bobines 1 et 2 selon la configuration fictive de démonstration.","Permuter les deux bobines, remonter les connecteurs puis effectuer un cycle de contrôle.","Relever les DTC sans les effacer automatiquement."],required_tools=["Lecteur OBD en lecture seule","Outillage manuel isolé"],expected_results=[{"result_id":"fault_moved_to_cylinder_2","label":"Le défaut se déplace vers le cylindre 2","meaning":"La bobine déplacée devient fortement suspecte.","next_action":"Contrôle de confirmation de la bobine."},{"result_id":"fault_stayed_on_cylinder_1","label":"Le défaut reste sur le cylindre 1","meaning":"La bobine est moins probable ; poursuivre sur bougie/injection.","next_action":"Inspecter et comparer la bougie du cylindre 1."},{"result_id":"test_unavailable","label":"Test impossible","meaning":"Aucune conclusion possible.","next_action":"Documenter le blocage et choisir une alternative."}],safety_notes=["Données et procédure fictives : ne pas appliquer à un véhicule réel.","Contact coupé, moteur froid ; suivre les règles de sécurité de l’atelier."],source_ids=[source_id],source_references=[source_ref],verification_status="verified")

def _synthesize_and_record(db,session,ctx):
    started=time.perf_counter(); raw=MockLLMProvider().synthesize(ctx).model_dump(); elapsed=int((time.perf_counter()-started)*1000); body=json.dumps(raw,sort_keys=True)
    db.add(AICall(session_id=session.id,provider="mock",model="deterministic-template-v1",prompt_version="diagnostic-v2",request_id=str(uuid.uuid4()),input_hash=hashlib.sha256(json.dumps(ctx,sort_keys=True).encode()).hexdigest(),output_hash=hashlib.sha256(body.encode()).hexdigest(),validation_status="valid",latency_ms=elapsed,token_usage=None))
    event(db,session.id,"ai_response_received",{"provider":"mock","validation_status":"valid"}); db.commit(); return raw

def analyze_generic(db:Session,session:DiagnosticSession,codes:list[str]):
    focus=codes[0].upper(); definition=resolve_dtc(db,focus,{"vehicle_id":session.vehicle_profile_id});source_ids=[definition.source["source_id"]] if definition and definition.source else [];source_refs=[definition.source] if definition and definition.source else []
    if definition and definition.documented:
        description=definition.description
        system=definition.category; system_reason=f"Exact standardized definition available: {description}."
        conclusion_status="insufficient_evidence"
        instructions=["Confirmer que le code est présent, mémorisé ou intermittent sans l’effacer automatiquement.","Relever le véhicule, la motorisation, le calculateur émetteur et les données figées disponibles.","Vérifier l’applicabilité de l’intitulé dans une documentation autorisée correspondant exactement au véhicule.","Documenter les symptômes avant de choisir une procédure de mesure spécifique."]
    else:
        description=definition.description if definition else "Definition unavailable for this vehicle configuration."
        system=definition.definition_type if definition else "unknown"; system_reason="No exact compatible definition is available."
        conclusion_status="manufacturer_specific_definition_unavailable" if definition and definition.definition_type=="manufacturer_specific" else "human_escalation_required"
        instructions=["Confirmer la lecture exacte du code et son statut sans l’effacer automatiquement.","Identifier marque, modèle, année, motorisation et calculateur ayant émis le code.","Consulter une documentation constructeur ou un fournisseur technique autorisé pour cette configuration.","Ne remplacer aucune pièce tant qu’une définition et une procédure applicables ne sont pas disponibles."]
    step=DiagnosticStep(session_id=session.id,step_order=1,title=f"Valider le contexte technique de {focus}",objective="Établir une définition applicable et un contexte fiable avant tout contrôle physique.",instructions=instructions,required_tools=["Lecteur OBD en lecture seule","Identification complète du véhicule","Documentation technique autorisée"],expected_results=[{"result_id":"context_documented","label":"Contexte et définition documentés","meaning":"Les informations minimales sont disponibles pour préparer une procédure dédiée.","next_action":"Clôturer ce parcours générique ou enrichir la base avec une règle validée."},{"result_id":"documentation_unavailable","label":"Documentation indisponible","meaning":"Le diagnostic ne peut pas progresser de façon sûre.","next_action":"Clôturer en état non résolu sans remplacer de pièce."}],safety_notes=["Parcours générique : aucune procédure physique spécifique n’est recommandée.","Ne jamais déduire une pièce défectueuse du seul code.","Aucune commande ECU ni suppression automatique de défaut."],source_ids=source_ids,source_references=source_refs,verification_status="verified" if source_refs else "unverified",status="current"); db.add(step); session.status="in_progress"; db.flush()
    event(db,session.id,"diagnostic_context_evaluated",{"codes":codes,"focus_code":focus,"catalog_match":bool(definition and definition.documented),"rule":"generic_dtc_context_v2","source_ids":source_ids})
    ctx={"summary":f"Analyse prudente de {focus}. {description}.","affected_systems":[{"name":system,"reason":system_reason}],"hypotheses":[],"step":{"title":step.title,"objective":step.objective,"instructions":step.instructions,"required_tools":step.required_tools,"expected_results":step.expected_results,"safety_notes":step.safety_notes,"source_ids":step.source_ids,"source_references":step.source_references,"verification_status":step.verification_status},"conclusion_status":conclusion_status,"limitations":["Insufficient evidence: no component hypothesis is produced.","A compatible manufacturer definition may be required.","Human escalation is required when the exact definition remains unavailable."]}
    return _synthesize_and_record(db,session,ctx)

def analyze(db: Session, session: DiagnosticSession):
    codes=[o.key.upper() for o in db.scalars(select(DiagnosticObservation).where(DiagnosticObservation.session_id==session.id,DiagnosticObservation.observation_type=="DTC").order_by(DiagnosticObservation.created_at)).all()]
    if "P0301" not in codes: return analyze_generic(db,session,codes)
    source=_source(db)
    if not source: raise ValueError("Corpus de démonstration absent ; exécuter python -m app.seed")
    existing=db.scalars(select(DiagnosticHypothesis).where(DiagnosticHypothesis.session_id==session.id)).all()
    if not existing:
        for h in _hypothesis_data(source.id):
            ref=source_reference(source,{"make":"Demo Motors","model":"DM-1","engine_code":"DEMO-ENG-01"});db.add(DiagnosticHypothesis(session_id=session.id,title=h["title"],suspected_component=h["component"],probability_score=h["score"],confidence_label=h["label"],reasoning=h["reason"],supporting_evidence=h["support"],contradicting_evidence=h["against"],source_ids=[source.id],source_references=[ref],verification_status="verified",status="active"))
        db.flush(); existing=db.scalars(select(DiagnosticHypothesis).where(DiagnosticHypothesis.session_id==session.id)).all()
    step=db.scalar(select(DiagnosticStep).where(DiagnosticStep.session_id==session.id,DiagnosticStep.status=="current"))
    if not step:
        s=first_step(source.id,source_reference(source,{"make":"Demo Motors","model":"DM-1","engine_code":"DEMO-ENG-01"})); step=DiagnosticStep(session_id=session.id,step_order=1,status="current",**s); db.add(step); db.flush()
    session.status="in_progress"; event(db,session.id,"hypothesis_generated",{"source_ids":[source.id],"rule":"p0301_initial_v1"})
    ctx={"hypotheses":[{"id":h.id,"title":h.title,"suspected_component":h.suspected_component,"probability_score":h.probability_score,"confidence_label":h.confidence_label,"supporting_evidence":h.supporting_evidence,"contradicting_evidence":h.contradicting_evidence,"source_ids":h.source_ids,"source_references":h.source_references,"verification_status":h.verification_status} for h in existing],"step":{"title":step.title,"objective":step.objective,"instructions":step.instructions,"required_tools":step.required_tools,"expected_results":step.expected_results,"safety_notes":step.safety_notes,"source_ids":step.source_ids,"source_references":step.source_references,"verification_status":step.verification_status},"conclusion_status":"testing_required"}
    return _synthesize_and_record(db,session,ctx)

def complete_step(db: Session, session: DiagnosticSession, step: DiagnosticStep, data: StepComplete):
    step.status="blocked" if data.state in NON_INFORMATIVE_RESULT_STATES else "completed"; step.result=data.model_dump(); step.technician_comment=data.comment; step.completed_at=now()
    hypotheses=db.scalars(select(DiagnosticHypothesis).where(DiagnosticHypothesis.session_id==session.id)).all(); by={h.suspected_component:h for h in hypotheses}; source=_source(db)
    if data.state in NON_INFORMATIVE_RESULT_STATES:
        event(db,session.id,"diagnostic_step_not_informative",{"step_id":step.id,"result":data.model_dump(),"probabilities_changed":False},session.technician_id);db.commit();return step
    if "ignition_coil_1" not in by:
        for hypothesis in hypotheses:
            hypothesis.status="unresolved"; hypothesis.supporting_evidence=[*hypothesis.supporting_evidence,f"Contexte technicien : {data.result_id}"]
        event(db,session.id,"diagnostic_step_completed",{"step_id":step.id,"result":data.model_dump(),"next_rule":"generic_close_or_enrich"},session.technician_id); db.commit(); return step
    if data.result_id not in {"fault_moved_to_cylinder_2","fault_stayed_on_cylinder_1"}:
        event(db,session.id,"diagnostic_result_requires_human_review",{"step_id":step.id,"result":data.model_dump(),"probabilities_changed":False,"next_rule":None},session.technician_id);db.commit();return step
    if data.result_id=="fault_moved_to_cylinder_2":
        h=by["ignition_coil_1"]; h.probability_score=92; h.confidence_label="high"; h.status="strengthened"; h.supporting_evidence=[*h.supporting_evidence,"Le raté a suivi la bobine vers le cylindre 2"]
        next_data=dict(title="Confirmer l’état de la bobine déplacée",objective="Confirmer l’hypothèse avant toute décision de réparation.",instructions=["Couper le contact et inspecter connecteur et faisceau.","Comparer avec une bobine connue conforme selon une procédure technique autorisée.","Documenter le résultat ; ne remplacer aucune pièce sur ce corpus fictif."],required_tools=["Multimètre selon procédure autorisée","Éclairage d’inspection"],expected_results=[{"result_id":"coil_confirmed","label":"Défaut confirmé par contrôle indépendant","meaning":"Hypothèse de bobine fortement étayée.","next_action":"Clôturer avec recommandation de validation professionnelle."},{"result_id":"coil_not_confirmed","label":"Contrôle non concluant","meaning":"La cause reste non résolue.","next_action":"Poursuivre le faisceau et l’alimentation."}],safety_notes=["Ne mesurer aucune haute tension sans équipement et procédure adaptés.","Corpus fictif réservé à la démonstration."],source_ids=[source.id],source_references=[source_reference(source,{"make":"Demo Motors","model":"DM-1","engine_code":"DEMO-ENG-01"})],verification_status="verified")
    else:
        h=by["ignition_coil_1"]; h.probability_score=25; h.confidence_label="low"; h.status="weakened"; h.contradicting_evidence=[*h.contradicting_evidence,"Le raté n’a pas suivi la bobine"]
        b=by["spark_plug_1"]; b.probability_score=72; b.confidence_label="medium"; b.status="strengthened"
        next_data=dict(title="Inspecter et comparer la bougie du cylindre 1",objective="Rechercher une cause d’allumage restant localisée au cylindre 1.",instructions=["Couper le contact et laisser refroidir.","Déposer la bougie uniquement selon une procédure autorisée.","Comparer visuellement avec le cylindre 2 et consigner l’état."],required_tools=["Outillage de bougie adapté","Éclairage"],expected_results=[{"result_id":"plug_abnormal","label":"Bougie anormale","meaning":"L’hypothèse bougie est renforcée.","next_action":"Effectuer un contrôle de confirmation."},{"result_id":"plug_normal","label":"Bougie comparable","meaning":"Poursuivre vers injection/étanchéité.","next_action":"Contrôler l’injection selon une source autorisée."}],safety_notes=["Moteur froid ; risque de brûlure et d’endommagement du filetage.","Corpus fictif, non applicable en atelier réel."],source_ids=[source.id],source_references=[source_reference(source,{"make":"Demo Motors","model":"DM-1","engine_code":"DEMO-ENG-01"})],verification_status="verified")
    order=(db.scalar(select(DiagnosticStep.step_order).where(DiagnosticStep.session_id==session.id).order_by(DiagnosticStep.step_order.desc())) or 1)+1
    nxt=DiagnosticStep(session_id=session.id,step_order=order,status="current",**next_data); db.add(nxt); event(db,session.id,"diagnostic_step_completed",{"step_id":step.id,"result":data.model_dump(),"next_rule":data.result_id},session.technician_id); db.flush(); event(db,session.id,"diagnostic_step_started",{"step_id":nxt.id}); db.commit(); return nxt
