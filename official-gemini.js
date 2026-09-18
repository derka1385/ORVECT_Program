/* Real backend integration for the ORVECT Pages interface.
 * The reasoning engine is whichever provider the backend is configured with
 * (Nebius Token Factory by default). API tokens live only in memory and no
 * provider credential ever enters this file.
 */
(()=>{
  const runtime=window.ORVECT_RUNTIME||{};
  if(runtime.mode!=='gemini')return; // runtime flag kept for compatibility: it means "talk to the real backend"
  const $=selector=>document.querySelector(selector);
  const ui=window.ORVECT_UI;
  let token='',activeCase=null,currentStep=null,activeVehicle=null,busy=false;
  $('#launchDiagnosis').textContent='Analyser avec ORVECT';
  $('#reanalyze').textContent='Réévaluer le dossier';
  const footer=$('[data-screen="4"] .footer-note');if(footer)footer.textContent='Analyse réelle produite par le moteur de raisonnement configuré et des preuves techniques récupérées. Les pistes doivent être confirmées par les contrôles ; les décisions de sécurité restent distinctes.';

  const SOURCE_LABELS={oem_manufacturer:'Constructeur / OEM',safety_authority:'Autorité de sécurité',technical_documentation:'Documentation technique',repair_technical_resource:'Ressource technique réparation',specialist_community:'Communauté spécialisée',general_web:'Web généraliste'};
  const SOURCE_RANK={oem_manufacturer:6,safety_authority:5,technical_documentation:4,repair_technical_resource:3,specialist_community:2,general_web:1};
  const CONFIDENCE_LABELS={low:'Faible',moderate:'Modérée',good:'Bonne',strong:'Élevée'};
  const sourceLabel=type=>SOURCE_LABELS[type]||String(type||'').replaceAll('_',' ');

  function base(){
    if(!runtime.apiBase)throw Error('Le service ORVECT n’est pas encore raccordé. Aucun résultat simulé ne sera généré.');
    const url=new URL(runtime.apiBase,location.href);
    if(url.protocol!=='https:'&&!['127.0.0.1','localhost'].includes(url.hostname))throw Error('Le service doit utiliser HTTPS.');
    return url.href.replace(/\/$/,'');
  }
  async function request(path,payload,method){
    token=await window.ORVECT_AUTH.token();
    const headers={'Content-Type':'application/json'};if(token)headers.Authorization='Bearer '+token;
    const response=await fetch(base()+path,{method:method||(payload===undefined?'GET':'POST'),headers,credentials:'omit',body:payload===undefined?undefined:JSON.stringify(payload),signal:AbortSignal.timeout(240000)});
    const body=await response.json().catch(()=>({}));
    if(response.status===401){token='';throw Error('Connexion expirée ou identifiants incorrects. Reconnectez-vous.');}
    if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:`Le service a répondu avec une erreur (${response.status}).`);
    return body;
  }
  window.ORVECT_SERVICE={request,activeCase:()=>activeCase};

  async function login(){
    base();await window.ORVECT_AUTH.ensure();await request('/auth/me');
    const vehicles=(await request('/vehicles')).items||[];
    // A loaded demo case names its vehicle; otherwise the Volkswagen demo stays the default.
    const wanted=ui.context().demo_vehicle_id;
    activeVehicle=vehicles.find(vehicle=>vehicle.is_demo_vehicle&&vehicle.id===wanted)||vehicles.find(vehicle=>vehicle.is_demo_vehicle&&vehicle.make==='Volkswagen')||null;
    if(!activeVehicle)throw Error('Aucun véhicule de démonstration n’est configuré pour ce compte.');
  }

  function el(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=String(text??'');return node;}
  function p(parent,text,tag='p'){const node=el(tag,'',text);parent.append(node);return node;}
  function list(parent,items){const ul=document.createElement('ul');for(const item of items||[])p(ul,item,'li');parent.append(ul);}
  function sourceNode(source){
    const box=el('div','ov-source');
    if(source.url){const a=el('a','',`${source.title||source.domain||source.source_id} ↗`);a.href=source.url;a.target='_blank';a.rel='noopener noreferrer nofollow';box.append(a);box.append(el('span','',`${sourceLabel(source.source_type)} · ${source.domain||''} · preuve externe non vérifiée`));}
    else{box.append(el('span','',`source_id: ${source.source_id}`));box.append(el('span','',`${source.source_type} · ${source.source_version} · ${source.verified?'VÉRIFIÉE':'NON VÉRIFIÉE'}`));}
    return box;
  }

  // --- live pipeline stages (screen 3) ------------------------------------
  function renderStages(progress){
    const panel=$('[data-analysis-stages]');if(!panel)return;panel.hidden=false;
    $('[data-stage-label]').textContent=progress?.label||'Démarrage de l’analyse';
    $('[data-stage-detail]').textContent=progress?.detail||'';
    const listNode=$('[data-stage-list]');listNode.replaceChildren();
    const index=progress?.index??0;
    (progress?.stages||[]).forEach((stage,i)=>{const li=el('li',i<index?'done':i===index?'active':'');li.append(el('b','',i<index?'✓':String(i+1).padStart(2,'0')),document.createTextNode(' '+stage.label));listNode.append(li);});
    $('[data-stage-elapsed]').textContent=progress?.elapsedMs?`${(progress.elapsedMs/1000).toFixed(1)} s écoulées`:'';
  }
  async function analyzeWithProgress(path,showStages){
    if(showStages)renderStages(null);
    const timer=showStages?setInterval(async()=>{try{renderStages(await request('/diagnostics/'+activeCase+'/progress'))}catch{}},700):null;
    try{return await request(path,{});}
    finally{if(timer)clearInterval(timer);const panel=$('[data-analysis-stages]');if(panel)panel.hidden=true;}
  }

  // --- report ---------------------------------------------------------------
  function collectEvidence(analysis){
    const seen=new Map();
    for(const item of [...(analysis.hypotheses||[]),...(analysis.nextChecks||[]),...(analysis.correlations||[])])
      for(const source of item.sources||[])if(source.url&&!seen.has(source.source_id))seen.set(source.source_id,source);
    return [...seen.values()].sort((a,b)=>(SOURCE_RANK[b.source_type]||0)-(SOURCE_RANK[a.source_type]||0));
  }
  function renderEvidence(analysis){
    const panel=$('[data-evidence]');if(!panel)return;panel.hidden=false;
    const evidence=collectEvidence(analysis);const research=analysis.researchMetadata||{};
    $('[data-evidence-count]').textContent=`${evidence.length} source${evidence.length===1?'':'s'} citée${evidence.length===1?'':'s'}`;
    const grid=$('[data-evidence-list]');grid.replaceChildren();
    for(const source of evidence){
      const rank=SOURCE_RANK[source.source_type]||0;
      const card=el('article',`ov-evidence-card ${rank>=5?'rank-high':rank<=2?'rank-low':''}`);
      const head=el('div','ov-evidence-card-head');head.append(el('span','eyebrow muted',sourceLabel(source.source_type)),document.createTextNode(' '),el('span','ov-domain',source.domain||''));card.append(head);
      card.append(el('h4','',source.title||source.domain||source.source_id));
      const foot=el('div','ov-foot');foot.append(el('span','',source.verified?'SOURCE VÉRIFIÉE':'NON VÉRIFIÉE'));
      const a=el('a','','Ouvrir la source ↗');a.href=source.url;a.target='_blank';a.rel='noopener noreferrer nofollow';foot.append(a);card.append(foot);grid.append(card);
    }
    $('[data-evidence-note]').textContent=evidence.length
      ?'Classées par niveau de fiabilité : constructeur et autorités de sécurité d’abord, communautés spécialisées ensuite. Une preuve issue du web reste non vérifiée et ne vaut pas une procédure constructeur.'
      :(research.researchTriggered?'Aucune source externe exploitable n’a été retenue pour ce dossier. Les pistes reposent sur la base interne ORVECT et restent à confirmer par les contrôles.':'La base interne ORVECT couvrait ce dossier : aucune recherche externe n’a été nécessaire.');
  }
  function renderConfidence(analysis){
    const panel=$('[data-confidence]');if(!panel)return;const c=analysis.confidence;panel.hidden=!c;if(!c)return;
    $('[data-confidence-score]').textContent=`${c.score} %`;
    const label=$('[data-confidence-label]');label.replaceChildren(el('span','','Qualité de l’étayage :'),document.createTextNode(' '),el('span','',CONFIDENCE_LABELS[c.label]||c.label));
    $('[data-confidence-bar]').style.width=`${c.score}%`;
    const factors=$('[data-confidence-factors]');factors.replaceChildren();for(const item of c.factors||[])p(factors,item,'li');
    const improve=$('[data-confidence-improve]');improve.replaceChildren();for(const item of c.improvedBy||[])p(improve,item,'li');
    improve.parentElement.hidden=!(c.improvedBy||[]).length;
  }
  function renderTransparency(analysis){
    const details=$('[data-transparency]');if(!details)return;const r=analysis.researchMetadata;details.hidden=!r;if(!r)return;
    const codes=(analysis.interpretedFaultCodes||[]).length,hyp=(analysis.hypotheses||[]).length,s=n=>n>1?'s':'';
    $('[data-transparency-summary]').textContent=r.researchTriggered
      ?`ORVECT a analysé ${codes} code${s(codes)} défaut, retenu ${hyp} hypothèse${s(hyp)}, lancé ${r.searchCount} recherche${s(r.searchCount)} technique${s(r.searchCount)} externe${s(r.searchCount)} et consulté ${r.externalSources} source${s(r.externalSources)}${r.fromCache?' (réutilisées depuis le cache)':''}.`
      :`ORVECT a analysé ${codes} code${s(codes)} défaut et retenu ${hyp} hypothèse${s(hyp)} à partir de sa base interne, sans recherche externe.`;
    const metrics=$('[data-transparency-metrics]');metrics.replaceChildren();
    for(const [label,value] of [['Recherche externe',r.researchTriggered?'Déclenchée':'Non nécessaire'],['Sources internes',String(r.internalSources??0)],['Sources externes',String(r.externalSources??0)],['Moteur',r.provider==='nebius'?'Nebius Token Factory':(r.provider||'—')]]){const box=el('div');box.append(el('p','eyebrow',label),el('strong','',value));metrics.append(box);}
    $('[data-transparency-model]').textContent=r.model?`modèle : ${r.model}${r.durationMs?` · ${(r.durationMs/1000).toFixed(1)} s`:''}${r.tokenUsage?.total_tokens?` · ${r.tokenUsage.total_tokens} tokens`:''}`:'';
    const reasons=$('[data-transparency-reasons]');reasons.hidden=!(r.researchReasons||[]).length;const rl=$('[data-transparency-reasons-list]');rl.replaceChildren();for(const item of r.researchReasons||[])rl.append(el('span','',item));
    const queries=$('[data-transparency-queries]');queries.hidden=!(r.queries||[]).length;const ql=$('[data-transparency-queries-list]');ql.replaceChildren();for(const item of r.queries||[])p(ql,item,'li');
    const mix=Object.entries(r.sourceMix||{}).sort((a,b)=>(SOURCE_RANK[b[0]]||0)-(SOURCE_RANK[a[0]]||0));
    const mixBox=$('[data-transparency-mix]');mixBox.hidden=!mix.length;const ml=$('[data-transparency-mix-list]');ml.replaceChildren();for(const [type,count] of mix)ml.append(el('span','',`${sourceLabel(type)} · ${count}`));
    const err=$('[data-transparency-error]');err.hidden=!r.researchError;err.textContent=r.researchError?`Vérification externe indisponible : ${r.researchError}. Le dossier s’appuie uniquement sur la base interne.`:'';
  }
  function renderTestPlan(analysis){
    const panel=$('[data-test-plan]');if(!panel)return;const checks=analysis.nextChecks||[];panel.hidden=!checks.length;
    const listNode=$('[data-test-plan-list]');listNode.replaceChildren();
    checks.forEach((check,index)=>{
      const li=el('li');const h3=el('h3');h3.append(el('span','ov-step',String(check.order||index+1).padStart(2,'0')),document.createTextNode(check.title));li.append(h3);
      p(li,check.objective);
      p(li,`Outillage : ${(check.requiredTools||[]).join(', ')||'—'} · difficulté ${check.estimatedDifficulty||'—'} · ${String(check.verificationStatus||'unverified').replaceAll('_',' ')}`,'p').className='ov-meta';
      if((check.instructions||[]).length)list(li,check.instructions);
      for(const expected of check.expectedResults||[]){const box=el('div','ov-outcome');box.append(el('strong','',expected.outcome),el('span','',expected.interpretation),el('span','',`→ ${expected.nextAction}`));li.append(box);}
      for(const source of check.sources||[])li.append(sourceNode(source));
      listNode.append(li);
    });
    const warnings=(analysis.warnings||[]).filter(w=>/remplac|replace/i.test(w)&&!/Décision réservée/.test(w));
    const box=$('[data-warnings]');box.hidden=!warnings.length;const wl=$('[data-warnings-list]');wl.replaceChildren();for(const item of warnings)p(wl,item,'li');
  }

  async function render(analysis,id){
    const detail=await request('/diagnostics/'+encodeURIComponent(id));
    if(detail.analysis_status!=='current')throw Error('Le backend n’a pas produit de résultat exploitable pour ce dossier.');
    activeCase=id;currentStep=(detail.steps||[]).find(step=>step.status==='current')?.id||null;
    ui.updateContext();ui.show(4);
    $('#diagSymptoms').textContent=analysis.caseSummary;
    const codes=$('#diagDtcList');codes.replaceChildren();
    for(const code of analysis.interpretedFaultCodes||[]){const card=el('article','dtc-card');p(card,code.code,'h3');p(card,code.meaning);p(card,code.sourceStatus==='ai_general_knowledge_unverified'?'APPROXIMATION IA · NON VÉRIFIÉE':code.sourceStatus==='provided_by_database'?'DÉFINITION DU CATALOGUE · SOURCE CONSERVÉE':'DÉFINITION INDISPONIBLE','p').className='eyebrow muted';for(const source of code.sources||[])card.append(sourceNode(source));codes.append(card);}
    const correlationText=$('#correlationText');let tags=$('#ovCorrelationTags');if(!tags){tags=el('div','ov-tags');tags.id='ovCorrelationTags';correlationText.before(tags);}tags.replaceChildren();
    for(const item of analysis.correlations||[]){for(const code of item.relatedCodes||[])tags.append(el('span','',code));tags.append(el('span','',String(item.relationshipType||'unresolved').replaceAll('_',' ')));}
    correlationText.textContent=(analysis.correlations||[]).map(item=>item.explanation).join('\n\n')||'Aucune relation suffisamment étayée proposée.';
    const hypotheses=$('#hypothesisContent');hypotheses.replaceChildren();$('#hypothesisCount').textContent=`${analysis.hypotheses.length} hypothèse${analysis.hypotheses.length>1?'s':''}`;
    analysis.hypotheses.forEach((h,index)=>{const card=el('article','dtc-card');p(card,`Hypothèse ${index+1} · pertinence ${Math.round(h.confidence*100)} %`,'p').className='eyebrow';p(card,h.label,'h3');const meta=el('div','ov-hyp-meta');meta.append(el('span','',h.status),el('span','',String(h.verificationStatus).replaceAll('_',' ')));card.append(meta);if((h.supportingEvidence||[]).length){p(card,'Éléments favorables','strong');list(card,h.supportingEvidence);}if((h.contradictingEvidence||[]).length){p(card,'Contradictions ou limites','strong');list(card,h.contradictingEvidence);}if((h.requiredConfirmation||[]).length){p(card,'Contrôles nécessaires','strong');list(card,h.requiredConfirmation);}for(const source of h.sources||[])card.append(sourceNode(source));hypotheses.append(card);});
    if(!analysis.hypotheses.length)p(hypotheses,analysis.finalConclusion.summary);
    const check=analysis.nextChecks[0];$('#checkTitle').textContent=check?.title||'Informations complémentaires nécessaires';$('#checkObjective').textContent=check?.objective||analysis.finalConclusion.summary;
    const instructions=$('.process-panel .instructions');instructions.replaceChildren();for(const instruction of check?.instructions||[])p(instructions,instruction,'li');
    $('#recordResult').disabled=!currentStep;
    const missing=$('.case-panel .missing');missing.replaceChildren();for(const item of analysis.missingInformation||[])p(missing,`${item.field} : ${item.reason} — ${item.howToObtain}`,'li');
    const safety=$('.hypothesis-panel .panel.dark');safety.replaceChildren();p(safety,'Évaluation de sécurité distincte','h3');p(safety,analysis.safetyAssessment.status);p(safety,analysis.safetyAssessment.explanation);p(safety,'Source : Safety Engine');
    const label=$('.hypothesis-panel > .status');if(label)label.textContent='ANALYSE ORVECT / HYPOTHÈSES À CONFIRMER';
    const measures=$('#diagMeasurements');if(measures){measures.replaceChildren();for(const m of (detail.observations||[]).filter(item=>item.observation_type==='measurement')){p(measures,m.key,'strong');p(measures,`${m.value?.value??''} ${m.unit||''}`);}}
    renderTestPlan(analysis);renderConfidence(analysis);renderEvidence(analysis);renderTransparency(analysis);
  }

  async function run(action){
    if(busy)return;busy=true;const controls=[...document.querySelectorAll('main input,main textarea,main select,main button')].map(node=>({node,disabled:node.disabled}));controls.forEach(({node})=>node.disabled=true);
    try{await login();await action();}
    finally{busy=false;controls.forEach(({node,disabled})=>node.disabled=disabled);$('#recordResult').disabled=!currentStep;}
  }
  function intercept(id,action){$(id).addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();run(action).catch(error=>{const notice=$('#diagnosticNotice')||$('#evidenceNotice')||$('#identificationNotice');if(notice){notice.textContent=error.message||'Action indisponible.';notice.classList.add('show','error');}});},true);}
  intercept('#launchDiagnosis',async()=>{
    const data=ui.context();
    if(!data.dtcs.length||data.dtcs.some(item=>item.status!=='confirmed'))throw Error('Confirmez chaque code avant l’analyse.');
    if(!data.symptoms.trim())throw Error('Décrivez les symptômes pour tester le raisonnement.');
    const vehicleId=activeVehicle?.id||runtime.vehicleId;if(!vehicleId)throw Error('Véhicule de démonstration non configuré côté site.');
    const vehicle=await request('/vehicles/'+encodeURIComponent(vehicleId)+'/configuration');
    if(!vehicle.vehicle?.is_demo_vehicle)throw Error('Ce parcours public de test exige un véhicule synthétique configuré.');
    const config=data.vehicle;
    if(config.make!==vehicle.vehicle.make||config.model!==vehicle.vehicle.model||config.engine!==vehicle.vehicle.engine_code||Number(config.year)!==vehicle.vehicle.year)throw Error('Pour ce test, chargez un cas de démonstration et conservez sa configuration synthétique.');
    const created=await request('/diagnostics',{vehicle_id:vehicleId,mileage:data.mileage,symptoms:data.symptoms,circumstances:data.circumstances});activeCase=created.id;
    await request('/diagnostics/'+activeCase+'/fault-codes',{fault_codes:data.dtcs.map(item=>({code:item.code,namespace:'sae_obd2',ecu:'ECU moteur',status:'unknown',freeze_frame:{},technician_verification:'confirmed',technician_note:'Code confirmé dans le parcours exploratoire de test.'}))});
    for(const measurement of data.measurements)await request('/diagnostics/'+activeCase+'/measurements',{name:measurement.name,value:measurement.value,unit:null,conditions:'Saisie du test exploratoire',source:'manual'});
    const analysis=await analyzeWithProgress('/diagnostics/'+activeCase+'/analyze',true);await render(analysis,activeCase);
  });
  intercept('#reanalyze',async()=>{if(!activeCase)throw Error('Lancez une première analyse.');await render(await analyzeWithProgress('/diagnostics/'+activeCase+'/reanalyze',false),activeCase);});
  intercept('#recordResult',async()=>{
    if(!activeCase||!currentStep)throw Error('Aucun contrôle courant dans ce dossier.');
    const state=$('#diagResult').value,outcome=$('#resultText').value;
    if(['positive','negative'].includes(state)&&!outcome.trim())throw Error('Décrivez l’observation informative.');
    await request('/diagnostics/'+activeCase+'/steps/'+currentStep+'/result',{state,outcome,comment:'Résultat saisi depuis le site officiel.'});
    await render(await analyzeWithProgress('/diagnostics/'+activeCase+'/reanalyze',false),activeCase);
  });
})();
