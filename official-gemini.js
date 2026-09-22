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

  const t=key=>window.ORVECT_I18N?.t(key)??key;
  const T=(key,vars)=>Object.entries(vars).reduce((text,[name,value])=>text.split('{'+name+'}').join(String(value)),t(key));
  const plural=(n,one,many)=>T(n===1?one:many,{n});
  // Server sentences that embed a count (« 3 sources externes … ») : look the {n} template up, then put the number back.
  const tn=text=>{const m=String(text||'').match(/\d+/);if(!m)return t(String(text||''));const key=String(text).replace(/\d+/,'{n}');const out=t(key);return out===key?t(String(text)):out.split('{n}').join(m[0]);};
  const SOURCE_LABELS={oem_manufacturer:'Constructeur / OEM',safety_authority:'Autorité de sécurité',technical_documentation:'Documentation technique',repair_technical_resource:'Ressource technique réparation',specialist_community:'Communauté spécialisée',general_web:'Web généraliste'};
  const STATUS_LABELS={likely:'probable',possible:'possible',unlikely:'peu probable',rejected:'écartée'};
  const VERIFICATION_LABELS={verified:'vérifiée',partially_verified:'partiellement vérifiée',unverified:'non vérifiée'};
  const DIFFICULTY_LABELS={easy:'facile',intermediate:'intermédiaire',advanced:'avancé'};
  const DURATION_RE=/(?:Durée estimée|Estimated duration|Uppskattad tid|Geschätzte Dauer)\s*:\s*([^.\n]+)\.?\s*/i;
  const MEANING_PREFIX='Approximation IA non vérifiée : ';
  const meaningText=meaning=>String(meaning||'').startsWith(MEANING_PREFIX)?t('Approximation IA non vérifiée :')+' '+String(meaning).slice(MEANING_PREFIX.length):t(String(meaning||''));
  const RELATION_LABELS={shared_root_cause:'cause racine commune',dependency:'dépendance',cascade:'cascade',contradiction:'contradiction',unresolved:'non résolu'};
  const SOURCE_RANK={oem_manufacturer:6,safety_authority:5,technical_documentation:4,repair_technical_resource:3,specialist_community:2,general_web:1};
  const CONFIDENCE_LABELS={low:'Faible',moderate:'Modérée',good:'Bonne',strong:'Élevée'};
  const sourceLabel=type=>t(SOURCE_LABELS[type]||String(type||'').replaceAll('_',' '));
  const label=(map,value)=>t(map[value]||String(value||'').replaceAll('_',' '));

  function base(){
    if(!runtime.apiBase)throw Error('Le service ORVECT n’est pas encore raccordé. Aucun résultat simulé ne sera généré.');
    const url=new URL(runtime.apiBase,location.href);
    if(url.protocol!=='https:'&&!['127.0.0.1','localhost'].includes(url.hostname))throw Error('Le service doit utiliser HTTPS.');
    return url.href.replace(/\/$/,'');
  }
  async function request(path,payload,method){
    token=await window.ORVECT_AUTH.token();
    const headers={'Content-Type':'application/json'};if(token)headers.Authorization='Bearer '+token;
    // A refused connection, a CORS rejection or a timeout all surface as a bare
    // "Failed to fetch". Naming what happened is the difference between a
    // technician retrying and a technician thinking the button is broken.
    let response;
    try{
      response=await fetch(base()+path,{method:method||(payload===undefined?'GET':'POST'),headers,credentials:'omit',body:payload===undefined?undefined:JSON.stringify(payload),signal:AbortSignal.timeout(240000)});
    }catch(error){
      throw Error(error?.name==='TimeoutError'
        ?t('Le service ORVECT n’a pas répondu à temps. Réessayez.')
        :t('Connexion réseau indisponible. Réessayez.'));
    }
    const body=await response.json().catch(()=>({}));
    if(response.status===401){token='';throw Error('Connexion expirée ou identifiants incorrects. Reconnectez-vous.');}
    if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:T('Le service a répondu avec une erreur ({status}).',{status:response.status}));
    return body;
  }
  async function upload(path,formData){
    token=await window.ORVECT_AUTH.token();
    const headers={};if(token)headers.Authorization='Bearer '+token;
    const response=await fetch(base()+path,{method:'POST',headers,credentials:'omit',body:formData,signal:AbortSignal.timeout(120000)});
    const body=await response.json().catch(()=>({}));
    if(response.status===401){token='';throw Error('Connexion expirée ou identifiants incorrects. Reconnectez-vous.');}
    if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:T('Le service a répondu avec une erreur ({status}).',{status:response.status}));
    return body;
  }
  async function uploadPendingPhotos(){
    const input=$('#checkPhoto');const files=[...(input?.files||[])];if(!files.length)return 0;
    const bad=files.find(file=>!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>8*1024*1024);
    if(bad)throw Error('Photo refusée : JPEG, PNG ou WebP, 8 Mo maximum.');
    for(const file of files){const data=new FormData();data.append('files',file);data.append('category',$('#checkPhotoCategory')?.value||'other');data.append('description',($('#checkPhotoNote')?.value||'').slice(0,500));await upload('/diagnostics/'+activeCase+'/images',data);}
    input.value='';if($('#checkPhotoNote'))$('#checkPhotoNote').value='';return files.length;
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
    if(source.url){const a=el('a','',`${source.title||source.domain||source.source_id} ↗`);a.href=source.url;a.target='_blank';a.rel='noopener noreferrer nofollow';box.append(a);box.append(el('span','',`${sourceLabel(source.source_type)} · ${source.domain||''} · ${t('preuve externe non vérifiée')}`));}
    else{box.append(el('span','',`source_id: ${source.source_id}`));box.append(el('span','',`${source.source_type} · ${source.source_version} · ${t(source.verified?'VÉRIFIÉE':'NON VÉRIFIÉE')}`));}
    return box;
  }

  // --- live pipeline stages (screen 3) ------------------------------------
  function renderStages(progress){
    const panel=$('[data-analysis-stages]');if(!panel)return;panel.hidden=false;
    $('[data-stage-label]').textContent=t(progress?.label||'Démarrage de l’analyse');
    $('[data-stage-detail]').textContent=progress?.detail||'';
    const listNode=$('[data-stage-list]');listNode.replaceChildren();
    const index=progress?.index??0;
    (progress?.stages||[]).forEach((stage,i)=>{const li=el('li',i<index?'done':i===index?'active':'');li.append(el('b','',i<index?'✓':String(i+1).padStart(2,'0')),document.createTextNode(' '+t(stage.label)));listNode.append(li);});
    // The bar tracks the stage the server actually reports, never a timer.
    const bar=$('[data-stage-bar]');
    if(bar){const total=progress?.total||0;bar.style.width=total?Math.round(((index+1)/total)*100)+'%':'0%';}
    $('[data-stage-elapsed]').textContent=progress?.elapsedMs?T('{s} s écoulées',{s:(progress.elapsedMs/1000).toFixed(1)}):'';
  }
  async function analyzeWithProgress(path,showStages){
    if(showStages)renderStages(null);
    const timer=showStages?setInterval(async()=>{try{renderStages(await request('/diagnostics/'+activeCase+'/progress'))}catch{}},700):null;
    try{return await request(path+'?language='+encodeURIComponent(window.ORVECT_I18N?.lang||document.documentElement.lang||'fr'),{});}
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
    $('[data-evidence-count]').textContent=plural(evidence.length,'{n} source citée','{n} sources citées');
    const grid=$('[data-evidence-list]');grid.replaceChildren();
    for(const source of evidence){
      const rank=SOURCE_RANK[source.source_type]||0;
      const card=el('article',`ov-evidence-card ${rank>=5?'rank-high':rank<=2?'rank-low':''}`);
      const head=el('div','ov-evidence-card-head');head.append(el('span','eyebrow muted',sourceLabel(source.source_type)),document.createTextNode(' '),el('span','ov-domain',source.domain||''));card.append(head);
      card.append(el('h4','',source.title||source.domain||source.source_id));
      const foot=el('div','ov-foot');foot.append(el('span','',t(source.verified?'SOURCE VÉRIFIÉE':'NON VÉRIFIÉE')));
      const a=el('a','',t('Ouvrir la source ↗'));a.href=source.url;a.target='_blank';a.rel='noopener noreferrer nofollow';foot.append(a);card.append(foot);grid.append(card);
    }
    $('[data-evidence-note]').textContent=t(evidence.length
      ?'Classées par niveau de fiabilité : constructeur et autorités de sécurité d’abord, communautés spécialisées ensuite. Une preuve issue du web reste non vérifiée et ne vaut pas une procédure constructeur.'
      :(research.researchTriggered?'Aucune source externe exploitable n’a été retenue pour ce dossier. Les pistes reposent sur la base interne ORVECT et restent à confirmer par les contrôles.':'La base interne ORVECT couvrait ce dossier : aucune recherche externe n’a été nécessaire.'));
  }
  function renderConfidence(analysis){
    const panel=$('[data-confidence]');if(!panel)return;const c=analysis.confidence;panel.hidden=!c;const miniBox=$('[data-confidence-mini]');if(miniBox)miniBox.hidden=!c;if(!c)return;
    $('[data-confidence-score]').textContent=`${c.score} %`;
    const mini=$('[data-confidence-mini]');if(mini){mini.hidden=false;$('[data-confidence-mini-score]').textContent=`${c.score} % · ${t(CONFIDENCE_LABELS[c.label]||c.label)}`;$('[data-confidence-mini-bar]').style.width=`${c.score}%`;}
    const qualityLabel=$('[data-confidence-label]');qualityLabel.replaceChildren(el('span','',t('Qualité de l’étayage :')),document.createTextNode(' '),el('span','',t(CONFIDENCE_LABELS[c.label]||c.label)));
    $('[data-confidence-bar]').style.width=`${c.score}%`;
    const factors=$('[data-confidence-factors]');factors.replaceChildren();for(const item of c.factors||[])p(factors,tn(item),'li');
    const improve=$('[data-confidence-improve]');improve.replaceChildren();for(const item of c.improvedBy||[])p(improve,tn(item),'li');
    improve.parentElement.hidden=!(c.improvedBy||[]).length;
  }
  function renderTransparency(analysis){
    const details=$('[data-transparency]');if(!details)return;const r=analysis.researchMetadata;details.hidden=!r;if(!r)return;
    const codes=plural((analysis.interpretedFaultCodes||[]).length,'{n} code défaut','{n} codes défaut'),hyp=plural((analysis.hypotheses||[]).length,'{n} hypothèse','{n} hypothèses');
    $('[data-transparency-summary]').textContent=r.researchTriggered
      ?T('ORVECT a analysé {codes}, retenu {hyp}, lancé {searches} et consulté {sources} {cache}.',{codes,hyp,searches:plural(r.searchCount,'{n} recherche technique externe','{n} recherches techniques externes'),sources:plural(r.externalSources,'{n} source','{n} sources'),cache:r.fromCache?t('(réutilisées depuis le cache)'):''}).replace(/\s+\./,'.')
      :T('ORVECT a analysé {codes} et retenu {hyp} à partir de sa base interne, sans recherche externe.',{codes,hyp});
    const metrics=$('[data-transparency-metrics]');metrics.replaceChildren();
    for(const [name,value] of [['Recherche externe',t(r.researchTriggered?'Déclenchée':'Non nécessaire')],['Sources internes',String(r.internalSources??0)],['Sources externes',String(r.externalSources??0)],['Moteur',r.provider==='nebius'?'Nebius Token Factory':(r.provider||'—')]]){const box=el('div');box.append(el('p','eyebrow',t(name)),el('strong','',value));metrics.append(box);}
    $('[data-transparency-model]').textContent=r.model?`${t('modèle')} : ${r.model}${r.durationMs?` · ${(r.durationMs/1000).toFixed(1)} s`:''}${r.tokenUsage?.total_tokens?` · ${r.tokenUsage.total_tokens} tokens`:''}`:'';
    const reasons=$('[data-transparency-reasons]');reasons.hidden=!(r.researchReasons||[]).length;const rl=$('[data-transparency-reasons-list]');rl.replaceChildren();for(const item of r.researchReasons||[])rl.append(el('span','',item));
    const queries=$('[data-transparency-queries]');queries.hidden=!(r.queries||[]).length;const ql=$('[data-transparency-queries-list]');ql.replaceChildren();for(const item of r.queries||[])p(ql,item,'li');
    const mix=Object.entries(r.sourceMix||{}).sort((a,b)=>(SOURCE_RANK[b[0]]||0)-(SOURCE_RANK[a[0]]||0));
    const mixBox=$('[data-transparency-mix]');mixBox.hidden=!mix.length;const ml=$('[data-transparency-mix-list]');ml.replaceChildren();for(const [type,count] of mix)ml.append(el('span','',`${sourceLabel(type)} · ${count}`));
    const err=$('[data-transparency-error]');err.hidden=!r.researchError;err.textContent=r.researchError?T('Vérification externe indisponible : {error}. Le dossier s’appuie uniquement sur la base interne.',{error:r.researchError}):'';
  }
  function renderTestPlan(analysis){
    const panel=$('[data-test-plan]');if(!panel)return;const checks=analysis.nextChecks||[];panel.hidden=!checks.length;
    const listNode=$('[data-test-plan-list]');listNode.replaceChildren();
    checks.forEach((check,index)=>{
      const li=el('li',(analysis.nextBestCheck?check.id===analysis.nextBestCheck.checkId:index===0)?'is-current':'');li.append(el('div','ov-num',String(check.order||index+1).padStart(2,'0')));
      const body=el('div','ov-body');p(body,check.title,'h3');
      const duration=(check.objective||'').match(DURATION_RE);const objective=(check.objective||'').replace(DURATION_RE,'').trim();
      if(objective)p(body,objective).className='ov-meta';
      const chips=el('div','ov-chips');if(duration)chips.append(el('span','time',`⏱ ${duration[1].trim()}`));for(const tool of check.requiredTools||[])chips.append(el('span','',tool));if(check.estimatedDifficulty)chips.append(el('span','',`${t('difficulté')} ${label(DIFFICULTY_LABELS,check.estimatedDifficulty)}`));body.append(chips);
      if((check.instructions||[]).length){const steps=el('ol','ov-steps');(check.instructions||[]).forEach((instruction,i)=>{const item=el('li');item.append(el('b','',String(i+1).padStart(2,'0')),document.createTextNode(instruction));steps.append(item);});body.append(steps);}
      if((check.expectedResults||[]).length){const outcomes=el('div','ov-outcomes');for(const expected of check.expectedResults||[]){const box=el('div','ov-outcome');box.append(el('strong','',expected.outcome),el('span','',expected.interpretation),el('span','',`→ ${expected.nextAction}`));outcomes.append(box);}body.append(outcomes);}
      for(const source of check.sources||[])body.append(sourceNode(source));
      li.append(body);listNode.append(li);
    });
    const warnings=(analysis.warnings||[]).filter(w=>/remplac|replace/i.test(w)&&!/Décision réservée/.test(w));
    const box=$('[data-warnings]');box.hidden=!warnings.length;const wl=$('[data-warnings-list]');wl.replaceChildren();for(const item of warnings)p(wl,item,'li');
  }

  async function render(analysis,id){
    const detail=await request('/diagnostics/'+encodeURIComponent(id));
    if(detail.analysis_status!=='current')throw Error('Le backend n’a pas produit de résultat exploitable pour ce dossier.');
    activeCase=id;currentStep=(detail.steps||[]).find(step=>step.status==='current')?.id||null;
    lastReport={analysis,detail};paint(analysis,detail);
  }
  let lastReport=null;
  window.addEventListener('orvect:language',()=>{if(lastReport)paint(lastReport.analysis,lastReport.detail);});
  function paint(analysis,detail){
    ui.updateContext();ui.show(4);
    $('[data-report-id]').textContent=T('Dossier {id}',{id:detail.case.id.slice(0,8).toUpperCase()});
    const safetyLabels={DO_NOT_DRIVE:'Ne pas rouler',STOP_AS_SOON_AS_SAFE:'S’arrêter dès que les conditions le permettent',UNKNOWN:'Sécurité non déterminée — avis technicien requis'};
    $('[data-result-safety]').textContent=label(safetyLabels,analysis.safetyAssessment.status);
    $('#diagSymptoms').textContent=analysis.caseSummary;
    const codes=$('#diagDtcList');codes.replaceChildren();
    for(const code of analysis.interpretedFaultCodes||[]){const card=el('article','dtc-card');p(card,code.code,'h3');p(card,meaningText(code.meaning));p(card,t(code.sourceStatus==='ai_general_knowledge_unverified'?'APPROXIMATION IA · NON VÉRIFIÉE':code.sourceStatus==='provided_by_database'?'DÉFINITION DU CATALOGUE · SOURCE CONSERVÉE':'DÉFINITION INDISPONIBLE'),'p').className='eyebrow muted';for(const source of code.sources||[])card.append(sourceNode(source));codes.append(card);}
    const correlationText=$('#correlationText');let tags=$('#ovCorrelationTags');if(!tags){tags=el('div','ov-tags');tags.id='ovCorrelationTags';correlationText.before(tags);}tags.replaceChildren();
    for(const item of analysis.correlations||[]){for(const code of item.relatedCodes||[])tags.append(el('span','',code));tags.append(el('span','',label(RELATION_LABELS,item.relationshipType||'unresolved')));}
    correlationText.textContent=(analysis.correlations||[]).map(item=>item.explanation).join('\n\n')||t('Aucune relation suffisamment étayée proposée.');
    const hypotheses=$('#hypothesisContent');hypotheses.replaceChildren();$('#hypothesisCount').textContent=plural(analysis.hypotheses.length,'{n} hypothèse','{n} hypothèses');
    const grid=el('div','ov-hyp-grid');hypotheses.append(grid);
    analysis.hypotheses.forEach((h,index)=>{
      const card=el('details',`ov-hyp${index===0?' is-lead':''}`);card.open=index===0;
      const heading=el('summary','ov-track-heading');const content=el('div','ov-track-content');
      const top=el('div','ov-hyp-top');top.append(el('span','ov-hyp-rank',index===0?t('HYPOTHÈSE PRINCIPALE · 01'):T('HYPOTHÈSE · {n}',{n:String(index+1).padStart(2,'0')})),el('span','ov-hyp-pct',`${Math.round(h.confidence*100)} %`));heading.append(top);
      p(heading,h.label,'h3');p(heading,t('Score de cohérence · pas une certitude'),'p').className='ov-score-note';heading.append(el('span','ov-track-toggle',t('Examiner la piste')));
      const bar=el('div','ov-bar');const fill=el('div','ov-bar-fill');fill.style.width=`${Math.round(h.confidence*100)}%`;bar.append(fill);content.append(bar);
      const meta=el('div','ov-hyp-meta');meta.append(el('span','',label(STATUS_LABELS,h.status)),el('span','',label(VERIFICATION_LABELS,h.verificationStatus)));content.append(meta);
      if((h.supportingEvidence||[]).length){content.append(el('strong','ov-h',t('Éléments favorables')));list(content,h.supportingEvidence);}
      if((h.contradictingEvidence||[]).length){content.append(el('strong','ov-h',t('Contradictions ou limites')));list(content,h.contradictingEvidence);}
      if((h.requiredConfirmation||[]).length){content.append(el('strong','ov-h',t('Contrôles nécessaires')));list(content,h.requiredConfirmation);}
      if((h.sources||[]).length){
        const references=el('details','ov-references');references.append(el('summary','',plural(h.sources.length,'Voir la référence','Voir les {n} références')));
        for(const source of h.sources)references.append(sourceNode(source));
        content.append(references);
      }
      card.append(heading,content);grid.append(card);
    });
    if(!analysis.hypotheses.length)p(hypotheses,analysis.finalConclusion.summary);
    // ORVECT picks the next check itself, deterministically; the plan below
    // keeps the full reasoning order. Fall back to the plan's first entry.
    const best=analysis.nextBestCheck?.checkId;
    const check=(best&&analysis.nextChecks.find(item=>item.id===best))||analysis.nextChecks[0];$('#checkTitle').textContent=check?.title||t('Informations complémentaires nécessaires');$('#checkObjective').textContent=(check?.objective||analysis.finalConclusion.summary||'').replace(/Durée estimée\s*:/i,t('Durée estimée :'));
    const rationale=$('[data-check-rationale]');rationale.replaceChildren();
    rationale.hidden=!(analysis.nextBestCheck?.rationale||[]).length;
    if(!rationale.hidden){p(rationale,t('Pourquoi ce contrôle ?'),'strong');list(rationale,analysis.nextBestCheck.rationale);}
    const stepLabel=$('.process-panel .check-card .eyebrow');stepLabel.textContent=check?T('Contrôle {n} · recommandé',{n:String(check.order).padStart(2,'0')}):t('Compléter les preuves');
    const instructions=$('.process-panel .instructions');instructions.replaceChildren();for(const instruction of check?.instructions||[])p(instructions,instruction,'li');
    $('#recordResult').disabled=!currentStep;
    const missing=$('.case-panel .missing');missing.replaceChildren();for(const item of analysis.missingInformation||[])p(missing,`${item.field} : ${item.reason} — ${item.howToObtain}`,'li');
    const safety=$('.hypothesis-panel .panel.dark');safety.replaceChildren();p(safety,t('Évaluation de sécurité distincte'),'h3');p(safety,t(analysis.safetyAssessment.status));p(safety,t(analysis.safetyAssessment.explanation));p(safety,t('Source : Safety Engine'));
    const statusLabel=$('.hypothesis-panel > .status');if(statusLabel)statusLabel.textContent=t('ANALYSE ORVECT / HYPOTHÈSES À CONFIRMER');
    const measures=$('#diagMeasurements');if(measures){measures.replaceChildren();for(const m of (detail.observations||[]).filter(item=>item.observation_type==='measurement')){p(measures,m.key,'strong');p(measures,`${m.value?.value??''} ${m.unit||''}`);}}
    renderTestPlan(analysis);renderConfidence(analysis);renderEvidence(analysis);renderTransparency(analysis);
  }

  async function run(action){
    if(busy)return;busy=true;clearFailure();const controls=[...document.querySelectorAll('main input,main textarea,main select,main button')].map(node=>({node,disabled:node.disabled}));controls.forEach(({node})=>node.disabled=true);
    try{await login();await action();}
    finally{busy=false;controls.forEach(({node,disabled})=>node.disabled=disabled);$('#recordResult').disabled=!currentStep;}
  }
  // Diagnostic failures get their own banner, on the screen the technician is
  // actually looking at. Two reasons it is not one of the existing notices:
  // those live on a fixed screen, so a refused analysis was announced on the
  // results page nobody was watching, and every one of them is cleared by an
  // anonymous 4.2 s timer that would wipe the explanation moments after it
  // appeared. An error stays until the next attempt.
  function errorBanner(){
    const screen=document.querySelector('.screen.active')||document.body;
    let box=screen.querySelector('[data-orvect-error]');
    if(!box){
      box=el('p','notice error');
      box.setAttribute('data-orvect-error','');
      box.setAttribute('role','alert');
      const anchor=screen.querySelector('.notice');
      if(anchor)anchor.after(box);else screen.prepend(box);
    }
    return box;
  }
  function clearFailure(){
    for(const box of document.querySelectorAll('[data-orvect-error]'))box.classList.remove('show');
  }
  function fail(error){
    const stages=$('[data-analysis-stages]');if(stages)stages.hidden=true;
    const box=errorBanner();
    box.textContent=error?.message||t('Action indisponible.');
    box.classList.add('show','error');
    box.scrollIntoView({block:'nearest',behavior:'instant'});
  }
  function intercept(id,action){$(id).addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();run(action).catch(fail);},true);}
  intercept('#launchDiagnosis',async()=>{
    renderStages(null);
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
  intercept('#attachPhoto',async()=>{
    if(!activeCase)throw Error('Lancez une première analyse avant de joindre une photo.');
    const added=await uploadPendingPhotos();if(!added)throw Error('Choisissez d’abord une photo (JPEG, PNG ou WebP).');
    await render(await analyzeWithProgress('/diagnostics/'+activeCase+'/reanalyze',false),activeCase);
    const notice=$('#diagnosticNotice');if(notice){notice.textContent=T('{n} photo(s) ajoutée(s) au dossier et analyse réévaluée.',{n:added});notice.classList.remove('error');notice.classList.add('show');}
  });
  intercept('#recordResult',async()=>{
    if(!activeCase||!currentStep)throw Error('Aucun contrôle courant dans ce dossier.');
    const state=$('#diagResult').value,outcome=$('#resultText').value;
    if(['positive','negative'].includes(state)&&!outcome.trim())throw Error('Décrivez l’observation informative.');
    await uploadPendingPhotos();
    await request('/diagnostics/'+activeCase+'/steps/'+currentStep+'/result',{state,outcome,comment:'Résultat saisi depuis le site officiel.'});
    await render(await analyzeWithProgress('/diagnostics/'+activeCase+'/reanalyze',false),activeCase);
  });
})();
