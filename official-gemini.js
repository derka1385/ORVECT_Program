/* Real backend integration for the existing ORVECT Pages interface.
 * API tokens live only in memory. Gemini credentials never enter this file.
 */
(()=>{
  const runtime=window.ORVECT_RUNTIME||{};
  if(runtime.mode!=='gemini')return;
  const $=selector=>document.querySelector(selector);
  const ui=window.ORVECT_UI;
  let token='',activeCase=null,currentStep=null,activeVehicle=null,busy=false;
  const banner=document.createElement('section');banner.className='panel';banner.setAttribute('aria-live','polite');
  const heading=document.createElement('strong');heading.textContent='GEMINI · MODE EXPLORATOIRE';
  const status=document.createElement('p');status.textContent='Hypothèses et interprétations approximatives non vérifiées. Connexion au service requise.';
  banner.append(heading,status);$('main').prepend(banner);
  $('#launchDiagnosis').textContent='Analyser avec Gemini';
  $('#reanalyze').textContent='Réévaluer avec Gemini';
  const footer=$('[data-screen="4"] .footer-note');if(footer)footer.textContent='Analyse réelle générée par Gemini. Les interprétations approximatives doivent être confirmées ; les décisions de sécurité restent distinctes.';
  function base(){
    if(!runtime.apiBase)throw Error('Le service Gemini du site officiel n’est pas encore raccordé. Aucun résultat simulé ne sera généré.');
    const url=new URL(runtime.apiBase,location.href);
    if(url.protocol!=='https:'&&!['127.0.0.1','localhost'].includes(url.hostname))throw Error('Le service doit utiliser HTTPS.');
    return url.href.replace(/\/$/,'');
  }
  async function request(path,payload,anonymous=false){
    if(!anonymous)token=await window.ORVECT_AUTH.token();
    const headers={'Content-Type':'application/json'};if(token&&!anonymous)headers.Authorization='Bearer '+token;
    const response=await fetch(base()+path,{method:payload===undefined?'GET':'POST',headers,credentials:'omit',body:payload===undefined?undefined:JSON.stringify(payload),signal:AbortSignal.timeout(240000)});
    const body=await response.json().catch(()=>({}));
    if(response.status===401){token='';throw Error('Connexion expirée ou identifiants incorrects. Reconnectez-vous.');}
    if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:`Le service a répondu avec une erreur (${response.status}).`);
    return body;
  }
  async function login(){
    base();await window.ORVECT_AUTH.ensure();await request('/auth/me');
    const vehicles=await request('/vehicles');
    activeVehicle=(vehicles.items||[]).find(vehicle=>vehicle.is_demo_vehicle&&vehicle.make==='Volkswagen')||null;
    if(!activeVehicle)throw Error('Aucun véhicule de démonstration n’est configuré pour ce compte.');
  }
  function p(parent,text,tag='p'){const node=document.createElement(tag);node.textContent=String(text??'');parent.append(node);return node;}
  function list(parent,items){const ul=document.createElement('ul');for(const item of items||[])p(ul,item,'li');parent.append(ul);}
  async function render(analysis,id){
    const detail=await request('/diagnostics/'+encodeURIComponent(id));
    if(!detail.case?.ai_model?.startsWith('gemini-'))throw Error('Le backend n’a pas produit de résultat Gemini. La simulation n’a pas été affichée.');
    activeCase=id;currentStep=(detail.steps||[]).find(step=>step.status==='current')?.id||null;
    ui.updateContext();ui.show(4);
    status.textContent=`Résultat Gemini enregistré · ${detail.case.ai_model} · dossier ${id.slice(0,8)}. Interprétations exploratoires non vérifiées.`;
    $('#diagSymptoms').textContent=analysis.caseSummary;
    const codes=$('#diagDtcList');codes.replaceChildren();
    for(const code of analysis.interpretedFaultCodes||[]){const card=document.createElement('article');card.className='dtc-card';p(card,code.code,'h3');p(card,code.meaning);p(card,code.sourceStatus==='ai_general_knowledge_unverified'?'APPROXIMATION GEMINI · NON VÉRIFIÉE':code.sourceStatus==='provided_by_database'?'DÉFINITION DU CATALOGUE · SOURCE CONSERVÉE':'DÉFINITION INDISPONIBLE');codes.append(card);}
    $('#correlationText').textContent=(analysis.correlations||[]).map(item=>item.explanation).join('\n\n')||'Aucune relation suffisamment étayée proposée.';
    const hypotheses=$('#hypothesisContent');hypotheses.replaceChildren();$('#hypothesisCount').textContent=`${analysis.hypotheses.length} hypothèse(s)`;
    for(const h of analysis.hypotheses){const card=document.createElement('article');card.className='dtc-card';p(card,h.label,'h3');p(card,'HYPOTHÈSE NON VÉRIFIÉE');p(card,'Éléments favorables');list(card,h.supportingEvidence);p(card,'Contradictions ou limites');list(card,h.contradictingEvidence);p(card,'Contrôles nécessaires');list(card,h.requiredConfirmation);hypotheses.append(card);}
    if(!analysis.hypotheses.length)p(hypotheses,analysis.finalConclusion.summary);
    const check=analysis.nextChecks[0];$('#checkTitle').textContent=check?.title||'Informations complémentaires nécessaires';$('#checkObjective').textContent=check?.objective||analysis.finalConclusion.summary;
    const instructions=$('.process-panel .instructions');instructions.replaceChildren();for(const instruction of check?.instructions||[])p(instructions,instruction,'li');
    $('#recordResult').disabled=!currentStep;
    const missing=$('.case-panel .missing');missing.replaceChildren();for(const item of analysis.missingInformation||[])p(missing,`${item.field} : ${item.reason} — ${item.howToObtain}`,'li');
    const safety=$('.hypothesis-panel .panel.dark');safety.replaceChildren();p(safety,'Évaluation de sécurité distincte','h3');p(safety,analysis.safetyAssessment.status);p(safety,analysis.safetyAssessment.explanation);p(safety,'Source : Safety Engine');
    const label=$('.hypothesis-panel > .status');if(label)label.textContent='GEMINI RÉEL / HYPOTHÈSES NON VÉRIFIÉES';
    const measures=$('#diagMeasurements');if(measures){measures.replaceChildren();for(const m of (detail.observations||[]).filter(item=>item.observation_type==='measurement')){p(measures,m.key,'strong');p(measures,`${m.value?.value??''} ${m.unit||''}`);}}
  }
  async function run(action){
    if(busy)return;busy=true;const controls=[...document.querySelectorAll('main input,main textarea,main select,main button')].map(node=>({node,disabled:node.disabled}));controls.forEach(({node})=>node.disabled=true);
    status.textContent='Connexion et analyse Gemini en cours…';
    try{await login();await action();}
    catch(error){status.textContent=error.message||'Service Gemini indisponible. Aucun résultat simulé généré.';}
    finally{busy=false;controls.forEach(({node,disabled})=>node.disabled=disabled);$('#recordResult').disabled=!currentStep;}
  }
  function intercept(id,action){$(id).addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();run(action);},true);}
  intercept('#launchDiagnosis',async()=>{
    const data=ui.context();
    if(!data.dtcs.length||data.dtcs.some(item=>item.status!=='confirmed'))throw Error('Confirmez chaque code avant l’analyse.');
    if(!data.symptoms.trim())throw Error('Décrivez les symptômes pour tester le raisonnement.');
    const vehicleId=activeVehicle?.id||runtime.vehicleId;if(!vehicleId)throw Error('Véhicule de démonstration non configuré côté site.');
    const vehicle=await request('/vehicles/'+encodeURIComponent(vehicleId)+'/configuration');
    if(!vehicle.vehicle?.is_demo_vehicle)throw Error('Ce parcours public de test exige le véhicule synthétique configuré.');
    const config=data.vehicle;
    if(config.make!==vehicle.vehicle.make||config.model!==vehicle.vehicle.model||config.engine!==vehicle.vehicle.engine_code||Number(config.year)!==vehicle.vehicle.year)throw Error('Pour ce test, chargez un exemple Golf et conservez sa configuration synthétique.');
    const created=await request('/diagnostics',{vehicle_id:vehicleId,mileage:data.mileage,symptoms:data.symptoms,circumstances:data.circumstances});activeCase=created.id;
    await request('/diagnostics/'+activeCase+'/fault-codes',{fault_codes:data.dtcs.map(item=>({code:item.code,namespace:'sae_obd2',ecu:'ECU moteur',status:'unknown',freeze_frame:{},technician_verification:'confirmed',technician_note:'Code confirmé dans le parcours exploratoire de test.'}))});
    for(const measurement of data.measurements)await request('/diagnostics/'+activeCase+'/measurements',{name:measurement.name,value:measurement.value,unit:null,conditions:'Saisie du test exploratoire',source:'manual'});
    const analysis=await request('/diagnostics/'+activeCase+'/analyze',{});await render(analysis,activeCase);
  });
  intercept('#reanalyze',async()=>{if(!activeCase)throw Error('Lancez une première analyse Gemini.');await render(await request('/diagnostics/'+activeCase+'/reanalyze',{}),activeCase);});
  intercept('#recordResult',async()=>{
    if(!activeCase||!currentStep)throw Error('Aucun contrôle courant dans ce dossier.');
    const state=$('#diagResult').value,outcome=$('#resultText').value;
    if(['positive','negative'].includes(state)&&!outcome.trim())throw Error('Décrivez l’observation informative.');
    await request('/diagnostics/'+activeCase+'/steps/'+currentStep+'/result',{state,outcome,comment:'Résultat saisi depuis le site officiel.'});
    await render(await request('/diagnostics/'+activeCase+'/reanalyze',{}),activeCase);
  });
})();
