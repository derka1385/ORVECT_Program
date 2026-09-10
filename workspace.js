/* ORVECT account workspace: real metrics, history, completion and review flows. */
(() => {
  const service = window.ORVECT_SERVICE;
  if (!service) return;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const date = value => value ? new Intl.DateTimeFormat({fr:'fr-FR',en:'en-GB',sv:'sv-SE',de:'de-DE'}[document.documentElement.lang] || 'fr-FR', {dateStyle:'medium', timeStyle:'short'}).format(new Date(value)) : '—';
  const labels = {
    completed:'Terminé', draft:'Actif', in_progress:'Actif', analyzing:'Analyse en cours',
    resolved:'Problème résolu', partially_resolved:'Partiellement résolu', not_resolved:'Non résolu', unknown_not_tested:'Non testé',
    problem_repaired:'Problème identifié et réparé', repair_pending:'Réparation en attente', no_repair_required:'Aucune réparation requise', inconclusive:'Diagnostic non concluant', referred_elsewhere:'Véhicule orienté ailleurs', other:'Autre'
  };
  const style = document.createElement('style');
  style.textContent = `
    .workspace-nav{display:flex;gap:7px;overflow:auto;margin:0 0 22px;padding:0 0 12px;border-bottom:1px solid var(--line);scrollbar-width:thin}
    .workspace-nav button{flex:0 0 auto;min-height:44px;border:1px solid var(--line);background:transparent;padding:10px 13px;font-size:12px;font-weight:650}
    .workspace-nav button:hover{border-color:var(--orange)}
    .orvect-dialog{width:min(1040px,calc(100% - 28px));max-height:calc(100vh - 28px);overflow:auto;border:1px solid var(--graphite);border-radius:0;background:var(--mineral);color:var(--graphite);padding:0}
    .orvect-dialog::backdrop{background:#101214c9}
    .dialog-head{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:18px;background:var(--graphite);color:var(--mineral);padding:18px 22px}
    .dialog-head h2{margin:0;font-size:23px}.dialog-close{min-width:44px;min-height:44px;border:1px solid #ffffff55;background:transparent;color:white;font-size:22px}
    .dialog-body{padding:24px}.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:18px 0 26px}
    .metric-card{border:1px solid var(--line);padding:16px;min-height:120px}.metric-card strong{display:block;font-size:34px}.metric-card span{font-size:12px;color:var(--muted)}
    .workspace-table{width:100%;border-collapse:collapse;font-size:13px}.workspace-table th,.workspace-table td{padding:12px 9px;border-top:1px solid var(--line);text-align:left;vertical-align:top}.workspace-table th{font-size:10px;text-transform:uppercase;letter-spacing:.06em}
    .workspace-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px}.workspace-form .wide{grid-column:1/-1}.checkbox-line{display:flex;gap:12px;align-items:flex-start;margin:18px 0}.checkbox-line input{width:22px;min-height:22px;margin:1px 0 0;flex:0 0 22px}
    .summary-box{grid-column:1/-1;background:var(--graphite);color:var(--mineral);padding:20px;margin-top:20px}.summary-box p{margin:7px 0}.workspace-message{grid-column:1/-1;min-height:24px;color:var(--danger)}
    .filter-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 18px}.filter-row .button{align-self:end}
    .review-card{border:1px solid var(--line);padding:16px;margin-top:10px;overflow-wrap:anywhere}.review-card pre{white-space:pre-wrap;font-size:11px}
    .account-workspace{display:grid;grid-template-columns:294px minmax(0,1fr);min-height:calc(100vh - 117px);background:var(--mineral)}
    .account-sidebar{display:flex;min-width:0;flex-direction:column;background:var(--graphite);color:var(--mineral);padding:31px 22px 28px}.account-sidebar h2{margin:12px 0 6px;font-size:24px}.account-sidebar-copy{margin:0;color:var(--alloy);font-size:13px}.account-menu{display:grid;min-width:0;max-width:100%;gap:5px;margin-top:20px}.account-menu button{min-height:57px;border:0;border-left:3px solid transparent;background:transparent;color:var(--alloy);padding:12px 14px;text-align:left;font-size:13px}.account-menu button:hover,.account-menu button.active{border-left-color:var(--orange);background:#232628;color:var(--mineral)}.account-plan-side{margin-top:auto;border:1px solid #ffffff35;padding:18px 14px;min-height:136px}.account-plan-side strong{display:block;margin-top:10px}.account-plan-side small{display:block;margin-top:8px;color:var(--alloy)}
    .account-main{min-width:0;padding:43px 40px 72px}.account-breadcrumb{color:var(--orange)}.account-main h1{margin:17px 0 8px;font-size:clamp(38px,4vw,56px);line-height:1;letter-spacing:-.045em}.account-lead{margin:0;color:var(--muted);font-size:17px}.account-demo-label{margin-top:13px;color:var(--muted);font-size:10px;text-transform:uppercase}.account-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:24px;margin-top:48px}.account-card{min-width:0;min-height:292px;border:1px solid var(--line);background:#ffffff42;padding:26px}.account-card.dark{background:var(--graphite);border-color:var(--graphite);color:var(--mineral)}.account-card h2{margin:20px 0 12px;font-size:26px;line-height:1.12;letter-spacing:-.025em}.account-card p{line-height:1.45}.account-card .eyebrow{color:var(--orange)}.account-profile{grid-column:span 5}.account-plan{grid-column:span 3}.account-activity{grid-column:span 4}.account-privacy{grid-column:span 6}.account-contributions{grid-column:span 3}.account-security{grid-column:span 3}.account-profile-line{display:flex;align-items:center;gap:16px;margin-top:20px}.account-avatar{display:grid;place-items:center;width:70px;height:70px;flex:0 0 70px;border-radius:50%;background:var(--graphite);color:var(--mineral);font-weight:700}.account-profile-line h2{margin:0 0 4px}.account-profile-line p{margin:0;color:var(--muted);overflow-wrap:anywhere}.account-org{margin:26px 0 12px;color:var(--muted)}.plan-badge{display:block;border:1px solid var(--orange);border-radius:999px;background:var(--mineral);color:var(--orange);padding:6px 10px;text-align:center;font-size:10px;font-weight:700;text-transform:uppercase}.account-note{color:var(--alloy);font-size:12px}.account-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:16px}.account-metric{background:#e8e7e3;padding:14px;min-height:98px}.account-metric strong{display:block;font-size:34px;line-height:1}.account-metric span{display:block;margin-top:12px;color:var(--muted);font-size:10px}.account-card-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:28px}.account-card-actions .button{min-height:50px}.dark .account-card-actions .button.primary{color:var(--graphite)}.account-toggle-row{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-top:22px}.account-toggle-copy strong{display:block}.account-toggle-copy small{display:block;margin-top:6px;color:var(--muted)}.privacy-toggle{position:relative;width:60px;height:34px;flex:0 0 60px;border:0;border-radius:999px;background:#a8aaad;padding:0}.privacy-toggle::after{content:"";position:absolute;top:4px;left:4px;width:26px;height:26px;border-radius:50%;background:white;transition:transform .18s}.privacy-toggle[aria-checked="true"]{background:var(--orange)}.privacy-toggle[aria-checked="true"]::after{transform:translateX(26px)}.account-status{min-height:20px;margin:15px 0 0;color:var(--muted);font-size:12px}.account-security .button{width:100%}.account-back{display:none}
    .account-workspace-tools{gap:12px;margin:0 0 34px;padding-bottom:20px}.account-workspace-tools button{min-height:58px;padding:13px 20px;font-size:14px}.account-workspace-tools button.active{border-color:var(--orange);background:var(--orange)}
    @media(max-width:1250px){.account-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.account-profile,.account-plan,.account-activity,.account-privacy,.account-contributions,.account-security{grid-column:span 1}.account-privacy{grid-column:1/-1}}
    @media(max-width:980px){.account-workspace{grid-template-columns:1fr}.account-sidebar{display:block;padding:22px}.account-menu{display:flex;overflow:auto}.account-menu button{flex:0 0 auto;min-height:44px;border-left:0;border-bottom:3px solid transparent}.account-menu button:hover,.account-menu button.active{border-left-color:transparent;border-bottom-color:var(--orange)}.account-plan-side{display:none}.account-back{display:inline-flex;margin-top:18px}.account-main{padding:34px 22px 60px}.account-grid{margin-top:34px}}
    @media(max-width:800px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.workspace-form,.filter-row{grid-template-columns:1fr}.workspace-form .wide{grid-column:auto}.workspace-table thead{display:none}.workspace-table,.workspace-table tbody,.workspace-table tr,.workspace-table td{display:block}.workspace-table tr{border:1px solid var(--line);margin-top:10px;padding:8px}.workspace-table td{border:0;padding:5px}.workspace-table td::before{content:attr(data-label);display:block;font-size:9px;text-transform:uppercase;color:var(--muted)}.account-grid{grid-template-columns:1fr}.account-profile,.account-plan,.account-activity,.account-privacy,.account-contributions,.account-security{grid-column:auto}.account-card{min-height:0}.account-metrics{gap:7px}.account-metric{padding:11px}.account-metric strong{font-size:28px}.account-card-actions .button{width:100%}.account-main h1{font-size:39px}}
  `;
  document.head.append(style);

  const nav = document.createElement('nav'); nav.className = 'workspace-nav'; nav.setAttribute('aria-label', 'Espace ORVECT');
  const actions = [['dashboard','Dashboard'],['new','Nouveau diagnostic'],['active','Diagnostics actifs'],['history','Historique'],['knowledge','Connaissances'],['suggest','Suggérer un DTC'],['account','Compte']];
  for (const [key, text] of actions) { const button=document.createElement('button'); button.type='button'; button.dataset.workspace=key; button.textContent=text; nav.append(button); }
  document.querySelector('main').prepend(nav);
  const diagnosticShell = document.querySelector('.shell');
  const accountRoot = document.createElement('section');
  accountRoot.className = 'account-workspace'; accountRoot.hidden = true; accountRoot.setAttribute('aria-labelledby', 'account-title');
  document.body.append(accountRoot);

  function dialog(title, body) {
    const node=document.createElement('dialog'); node.className='orvect-dialog'; node.innerHTML=`<header class="dialog-head"><h2>${escape(title)}</h2><button class="dialog-close" type="button" aria-label="Fermer">×</button></header><div class="dialog-body">${body}</div>`;
    document.body.append(node); node.querySelector('.dialog-close').onclick=()=>node.close(); node.addEventListener('cancel',()=>node.close()); node.showModal(); return node;
  }
  async function authenticated() {
    await window.ORVECT_AUTH.ensure(); const me=await service.request('/auth/me');
    if(me.role==='admin'&&!nav.querySelector('[data-workspace=review]')){const button=document.createElement('button');button.type='button';button.dataset.workspace='review';button.textContent='Revue admin';nav.append(button)}
    return me;
  }
  function failure(node, error) { const target=node.querySelector('.workspace-message') || node.querySelector('[role=status]'); if(target) target.textContent=error.message || 'Une erreur est survenue.'; }

  async function showDashboard() {
    await authenticated(); const data=await service.request('/workspace/dashboard'); const m=data.metrics;
    const node=dialog('Dashboard atelier', `<p class="eyebrow">${escape(data.account.product)}</p><h3>Forfait ${escape(data.account.plan)} · ${data.account.monthly_price_eur} €/mois</h3><div class="metric-grid"></div><h3>Diagnostics récents</h3><div class="recent-list"></div><p class="workspace-message" role="status"></p>`);
    const cards=[['Total',m.total_diagnostics],['Terminés',m.completed_diagnostics],['Actifs',m.active_diagnostics],['Résolus',m.resolved_diagnostics],['Non concluants',m.inconclusive_diagnostics],['Véhicules',m.vehicles_diagnosed],['DTC uniques',m.unique_dtcs],['Partagés',m.cases_shared]];
    node.querySelector('.metric-grid').innerHTML=cards.map(([label,value])=>`<div class="metric-card"><strong>${value}</strong><span>${escape(label)}</span></div>`).join('');
    renderRows(node.querySelector('.recent-list'), data.recent_diagnostics);
  }

  function renderRows(target, rows) {
    if (!rows.length) { target.innerHTML='<p class="muted">Aucun diagnostic pour le moment.</p>'; return; }
    target.innerHTML=`<table class="workspace-table"><thead><tr><th>Véhicule</th><th>DTC</th><th>Statut</th><th>Démarré</th><th>Terminé</th><th>Résultat</th></tr></thead><tbody>${rows.map(row=>`<tr><td data-label="Véhicule">${escape(row.vehicle.make)} ${escape(row.vehicle.model)} (${row.vehicle.year})</td><td data-label="DTC">${escape(row.dtcs.join(', ')||'—')}</td><td data-label="Statut">${escape(labels[row.status]||row.status)}</td><td data-label="Démarré">${date(row.started_at)}</td><td data-label="Terminé">${date(row.completed_at)}</td><td data-label="Résultat">${escape(labels[row.outcome]||labels[row.resolution_status]||'—')}</td></tr>`).join('')}</tbody></table>`;
  }

  async function showHistory(activeOnly=false) {
    await authenticated();
    const node=dialog(activeOnly?'Diagnostics actifs':'Historique des diagnostics', `<form class="filter-row"><label><span class="field-label">Statut</span><select name="status"><option value="">Tous</option><option value="active">Actifs</option><option value="completed">Terminés</option><option value="resolved">Résolus</option><option value="inconclusive">Non concluants</option></select></label><label><span class="field-label">Véhicule</span><input name="vehicle"></label><label><span class="field-label">DTC</span><input name="dtc"></label><button class="button primary">Filtrer</button></form><p class="muted">Les diagnostics terminés sont conservés. Toute correction crée un événement d’amendement.</p><div class="history-list"></div><p class="workspace-message" role="status"></p>`);
    const form=node.querySelector('form'); if(activeOnly) form.elements.status.value='active';
    const load=async()=>{const params=new URLSearchParams(new FormData(form)); for(const [key,value] of [...params])if(!value)params.delete(key); const data=await service.request('/workspace/history?'+params);renderRows(node.querySelector('.history-list'),data.items)};
    form.onsubmit=event=>{event.preventDefault();load().catch(error=>failure(node,error))}; await load();
  }

  function closeAccount() {
    accountRoot.hidden = true;
    diagnosticShell.hidden = false;
  }

  function downloadAccountData(payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = `orvect-account-${new Date().toISOString().slice(0,10)}.json`;
    document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  }

  async function showSettings() {
    const me = await authenticated();
    const [settings, dashboard, firebaseUser] = await Promise.all([
      service.request('/workspace/settings'),
      service.request('/workspace/dashboard'),
      window.ORVECT_AUTH.currentUser()
    ]);
    const metrics = dashboard.metrics;
    const email = firebaseUser?.email || me.email || '—';
    const profileName = firebaseUser?.displayName || 'Utilisateur ORVECT';
    const initials = firebaseUser?.displayName ? profileName.split(/\s+/).map(part => part[0]).join('').slice(0,2).toUpperCase() : 'OR';
    const sharingEnabled = settings.data_sharing_preference === 'ASK_EVERY_TIME';
    accountRoot.innerHTML = `
      <aside class="account-sidebar">
        <p class="eyebrow">Mon espace</p><h2>Compte ORVECT</h2><p class="account-sidebar-copy">Gestion du compte</p>
        <nav class="account-menu" aria-label="Gestion du compte">
          <button class="active" type="button" data-account-target="overview">Vue d’ensemble</button>
          <button type="button" data-account-target="profile">Profil</button>
          <button type="button" data-account-target="activity">Utilisation</button>
          <button type="button" data-account-target="privacy">Données & confidentialité</button>
          <button type="button" data-account-target="contributions">Contributions</button>
        </nav>
        <button class="button account-back" type="button" data-account-close>Retour au diagnostic</button>
        <div class="account-plan-side"><p class="eyebrow">Plan actuel</p><strong>Bêta · Gratuit</strong><small>Prototype ORVECT</small></div>
      </aside>
      <main class="account-main" id="overview">
        <nav class="workspace-nav account-workspace-tools" aria-label="Espace ORVECT">
          <button type="button" data-account-workspace="dashboard">Dashboard</button>
          <button type="button" data-account-workspace="new">Nouveau diagnostic</button>
          <button type="button" data-account-workspace="active">Diagnostics actifs</button>
          <button type="button" data-account-workspace="history">Historique</button>
          <button type="button" data-account-workspace="knowledge">Connaissances</button>
          <button type="button" data-account-workspace="suggest">Suggérer un DTC</button>
          <button class="active" type="button" data-account-workspace="account">Compte</button>
        </nav>
        <p class="eyebrow account-breadcrumb">Mon espace / Compte</p>
        <h1 id="account-title">Gérer votre compte ORVECT.</h1>
        <p class="account-lead">Profil, plan, activité, préférences de partage et contributions à la base de diagnostic.</p>
        <p class="account-demo-label">Données de votre espace sécurisé</p>
        <div class="account-grid">
          <article class="account-card account-profile" id="profile"><p class="eyebrow">Profil</p><div class="account-profile-line"><span class="account-avatar">${escape(initials)}</span><div><h2>${escape(profileName)}</h2><p>${escape(email)}</p></div></div><p class="account-org">Organisation / garage · non renseigné</p><button class="button" type="button" data-profile-info>Profil Firebase vérifié</button><p class="account-status" data-profile-status aria-live="polite"></p></article>
          <article class="account-card dark account-plan"><p class="eyebrow">Plan actuel</p><h2>Bêta · Gratuit</h2><p class="account-note">Accès au prototype, aux diagnostics et aux fonctions de contribution.</p><span class="plan-badge">Actif</span><p class="account-note">Aucune facturation pendant la bêta.</p></article>
          <article class="account-card account-activity" id="activity"><p class="eyebrow">Activité</p><h2>Votre utilisation</h2><div class="account-metrics"><div class="account-metric"><strong>${metrics.total_diagnostics}</strong><span>Diagnostics</span></div><div class="account-metric"><strong>${metrics.cases_shared}</strong><span>Cas partagés</span></div><div class="account-metric"><strong>${metrics.unique_dtcs}</strong><span>DTC uniques</span></div></div><p class="account-status">Compteurs calculés depuis votre espace atelier.</p></article>
          <article class="account-card account-privacy" id="privacy"><p class="eyebrow">Données & confidentialité</p><h2>Partage des diagnostics terminés</h2><p class="muted">Choisissez si ORVECT doit vous proposer de contribuer à la base avec un cas validé. Aucun diagnostic n’est partagé sans action explicite du technicien.</p><div class="account-toggle-row"><div class="account-toggle-copy"><strong>Me proposer le partage à la fin d’un diagnostic</strong><small>DTC, contexte véhicule et résolution confirmée uniquement.</small></div><button class="privacy-toggle" type="button" role="switch" aria-checked="${sharingEnabled}" aria-label="Préférence de partage"></button></div><div class="account-card-actions"><button class="button" type="button" data-shared>Voir les données partagées</button><button class="button" type="button" data-export>Exporter mes données</button></div><p class="account-status" data-privacy-status role="status"></p></article>
          <article class="account-card dark account-contributions" id="contributions"><p class="eyebrow">Contributions</p><h2>Enrichir la base DTC</h2><p class="account-note">Proposez un code erreur, une interprétation ou un cas atelier. Chaque ajout reste soumis à validation.</p><strong>${settings.cases_contributed} contribution(s) enregistrée(s)</strong><div class="account-card-actions"><button class="button primary" type="button" data-suggest>Ajouter un code erreur</button></div></article>
          <article class="account-card account-security"><p class="eyebrow">Sécurité</p><h2>Session & accès</h2><p class="muted">Vos identifiants sont gérés par Firebase Authentication.</p><strong>Session actuelle · active</strong><div class="account-card-actions"><button class="button" type="button" data-password>Modifier le mot de passe</button><button class="button" type="button" data-logout>Se déconnecter</button></div><p class="account-status" data-security-status role="status"></p></article>
        </div>
      </main>`;
    diagnosticShell.hidden = true; accountRoot.hidden = false; window.scrollTo({top:0, behavior:'smooth'});

    accountRoot.querySelectorAll('[data-account-target]').forEach(button => button.onclick = () => {
      accountRoot.querySelectorAll('[data-account-target]').forEach(item => item.classList.toggle('active', item === button));
      accountRoot.querySelector('#' + button.dataset.accountTarget)?.scrollIntoView({behavior:'smooth', block:'start'});
    });
    accountRoot.querySelector('.account-workspace-tools').onclick = event => {
      const key = event.target.dataset.accountWorkspace; if (!key) return;
      if (key === 'account') { accountRoot.querySelector('#overview').scrollIntoView({behavior:'smooth', block:'start'}); return; }
      runWorkspaceAction(key);
    };
    accountRoot.querySelector('[data-account-close]').onclick = () => window.ORVECT_UI.show(1);
    accountRoot.querySelector('[data-profile-info]').onclick = () => accountRoot.querySelector('[data-profile-status]').textContent = 'Adresse e-mail vérifiée et session protégée par Firebase.';
    accountRoot.querySelector('[data-shared]').onclick = () => { closeAccount(); showHistory(false).catch(error => dialog('Action indisponible', `<p>${escape(error.message)}</p>`)); };
    accountRoot.querySelector('[data-export]').onclick = () => downloadAccountData({ exported_at: new Date().toISOString(), user: { email: me.email, role: me.role }, settings, account: dashboard.account, metrics });
    accountRoot.querySelector('[data-suggest]').onclick = () => showSuggestion().catch(error => dialog('Action indisponible', `<p>${escape(error.message)}</p>`));
    accountRoot.querySelector('[data-password]').onclick = async () => {
      const status = accountRoot.querySelector('[data-security-status]'); status.textContent = '';
      try { status.textContent = await window.ORVECT_AUTH.resetPassword(); } catch (error) { status.textContent = error.message; }
    };
    accountRoot.querySelector('[data-logout]').onclick = () => window.ORVECT_AUTH.logout();
    accountRoot.querySelector('.privacy-toggle').onclick = async event => {
      const toggle = event.currentTarget; const next = toggle.getAttribute('aria-checked') !== 'true'; const status = accountRoot.querySelector('[data-privacy-status]');
      toggle.disabled = true; status.textContent = '';
      try {
        await service.request('/workspace/settings', { data_sharing_preference: next ? 'ASK_EVERY_TIME' : 'DO_NOT_SHARE_BY_DEFAULT' }, 'PUT');
        toggle.setAttribute('aria-checked', String(next)); status.textContent = 'Préférence enregistrée. Chaque partage exige toujours une action explicite.';
      } catch (error) { status.textContent = error.message || 'Une erreur est survenue.'; }
      finally { toggle.disabled = false; }
    };
  }

  async function showSuggestion() {
    await authenticated(); const node=dialog('Suggérer un code défaut manquant', `<form class="workspace-form"><label><span class="field-label">DTC / code défaut *</span><input name="code" required maxlength="80"></label><label><span class="field-label">Marque / constructeur *</span><input name="manufacturer" required maxlength="120"></label><label><span class="field-label">ECU / module</span><input name="ecu_module" maxlength="120"></label><label><span class="field-label">Sous-code</span><input name="subcode" maxlength="80"></label><label class="wide"><span class="field-label">Description *</span><textarea name="description" required maxlength="5000"></textarea></label><label><span class="field-label">Véhicule</span><input name="vehicle"></label><label><span class="field-label">Moteur</span><input name="engine"></label><label><span class="field-label">Plateforme</span><input name="platform"></label><label><span class="field-label">Source / référence</span><input name="source_reference"></label><label class="wide"><span class="field-label">Notes</span><textarea name="notes"></textarea></label><label class="checkbox-line wide"><input name="attested" type="checkbox" required><span>Je confirme que cette information repose sur une source de diagnostic ou une observation réelle du véhicule.</span></label><div class="wide button-row"><button type="button" class="button" data-check>Vérifier les doublons</button><button class="button primary">Envoyer pour revue</button></div><p class="workspace-message" role="status"></p></form>`);
    const form=node.querySelector('form'); const payload=()=>Object.fromEntries([...new FormData(form).entries()].map(([k,v])=>[k,v]));
    const data=()=>({...payload(),attested:form.elements.attested.checked});
    node.querySelector('[data-check]').onclick=async()=>{try{const check=await service.request('/dtc-submissions/check',data());node.querySelector('.workspace-message').style.color='inherit';node.querySelector('.workspace-message').textContent=check.possible_duplicate?(check.conflict_detected?'Entrée similaire trouvée avec une description différente. Vous pouvez ajouter votre preuve.':'Doublon possible. Vous pouvez envoyer une preuve complémentaire.'):'Aucune entrée similaire trouvée.'}catch(error){failure(node,error)}};
    form.onsubmit=async event=>{event.preventDefault();try{const result=await service.request('/dtc-submissions',data());node.querySelector('.workspace-message').style.color='inherit';node.querySelector('.workspace-message').textContent=`Suggestion enregistrée avec le statut ${result.submission.status}. Elle ne modifie pas la base DTC de confiance.`;form.querySelectorAll('input,textarea,button,select').forEach(field=>field.disabled=true)}catch(error){failure(node,error)}};
  }

  async function showKnowledge() {
    await authenticated(); dialog('Connaissances ORVECT', `<p>Les définitions documentées, les interprétations Gemini et les cas atelier restent séparés par leur provenance.</p><div class="review-card"><h3>Base de confiance</h3><p>Seules les données revues et promues par un administrateur peuvent rejoindre la connaissance de production.</p></div><div class="review-card"><h3>Cas atelier</h3><p>Les cas partagés restent dans la file <strong>PENDING_REVIEW</strong>, ou sont signalés comme conflit. Ils ne remplacent jamais une définition existante.</p></div>`);
  }

  async function showCompletion() {
    await authenticated(); const caseId=service.activeCase(); if(!caseId) throw Error('Lancez une analyse avant de terminer le diagnostic.'); const detail=await service.request('/diagnostics/'+encodeURIComponent(caseId));
    const node=dialog('Diagnostic terminé', `<form class="workspace-form"><label><span class="field-label">Statut de résolution</span><select name="resolution_status"><option value="problem_repaired">Problème identifié et réparé</option><option value="repair_pending">Problème identifié, réparation en attente</option><option value="no_repair_required">Problème identifié, aucune réparation requise</option><option value="inconclusive">Diagnostic non concluant</option><option value="referred_elsewhere">Véhicule orienté ailleurs</option><option value="other">Autre</option></select></label><label><span class="field-label">Hypothèse ORVECT associée</span><select name="selected_hypothesis_id"><option value="">Aucune sélection</option>${(detail.hypotheses||[]).map(item=>`<option value="${escape(item.id)}">${escape(item.title)}</option>`).join('')}</select></label><label class="wide"><span class="field-label">Cause confirmée</span><textarea name="confirmed_cause"></textarea></label><label><span class="field-label">Action / réparation</span><select name="repair_action_type"><option value="component_replaced">Composant remplacé</option><option value="wiring_repaired">Câblage réparé</option><option value="cleaning">Nettoyage</option><option value="software_update">Mise à jour logicielle</option><option value="coding_adaptation">Codage / adaptation</option><option value="no_repair">Aucune réparation</option><option value="other">Autre</option></select></label><label><span class="field-label">Composants impliqués</span><input name="components" placeholder="Séparer par des virgules"></label><label class="wide"><span class="field-label">Détails de la réparation</span><textarea name="repair_action_details"></textarea></label><label><span class="field-label">Confiance dans la cause racine</span><select name="root_cause_confidence"><option value="successful_repair">Confirmée par réparation réussie</option><option value="measurement_test">Confirmée par mesure / test</option><option value="strongly_suspected">Fortement suspectée</option><option value="not_confirmed">Non confirmée</option></select></label><label><span class="field-label">Résultat après réparation</span><select name="post_repair_result"><option value="resolved">Problème résolu</option><option value="partially_resolved">Partiellement résolu</option><option value="not_resolved">Non résolu</option><option value="unknown_not_tested">Inconnu / non testé</option></select></label><label><span class="field-label">DTC après réparation</span><select name="dtc_after_repair"><option value="cleared_no_return">Effacé et non revenu</option><option value="returned">Revenu</option><option value="not_checked">Non contrôlé</option><option value="not_applicable">Sans objet</option></select></label><label class="wide"><span class="field-label">Notes technicien</span><textarea name="technician_notes"></textarea></label><label class="checkbox-line wide"><input name="consent" type="checkbox"><span>J’accepte de partager les données anonymisées de ce cas avec ORVECT afin d’améliorer les connaissances de diagnostic.</span></label><section class="summary-box"><p class="eyebrow">Résultat du diagnostic</p><p><strong>Cause confirmée :</strong> <span data-summary="cause">À renseigner</span></p><p><strong>Réparation :</strong> <span data-summary="repair">Composant remplacé</span></p><p><strong>Résultat :</strong> <span data-summary="result">Problème résolu</span></p><p><strong>Partage anonymisé :</strong> <span data-summary="share">Non</span></p></section><div class="wide button-row"><button class="button primary">Terminer le diagnostic</button></div><p class="workspace-message" role="status"></p></form>`);
    const form=node.querySelector('form');
    const summary=()=>{node.querySelector('[data-summary=cause]').textContent=form.elements.confirmed_cause.value||form.elements.selected_hypothesis_id.selectedOptions[0]?.textContent||'À renseigner';node.querySelector('[data-summary=repair]').textContent=form.elements.repair_action_type.selectedOptions[0].textContent+(form.elements.repair_action_details.value?` · ${form.elements.repair_action_details.value}`:'');node.querySelector('[data-summary=result]').textContent=form.elements.post_repair_result.selectedOptions[0].textContent;node.querySelector('[data-summary=share]').textContent=form.elements.consent.checked?'Oui':'Non'};
    form.addEventListener('input',summary); summary();
    form.onsubmit=async event=>{event.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;try{await service.request(`/diagnostics/${encodeURIComponent(caseId)}/consent`,{consent:form.elements.consent.checked});const result=await service.request(`/diagnostics/${encodeURIComponent(caseId)}/complete`,{resolution_status:form.elements.resolution_status.value,confirmed_cause:form.elements.confirmed_cause.value,selected_hypothesis_id:form.elements.selected_hypothesis_id.value||null,repair_action_type:form.elements.repair_action_type.value,repair_action_details:form.elements.repair_action_details.value,components_involved:form.elements.components.value.split(',').map(v=>v.trim()).filter(Boolean),root_cause_confidence:form.elements.root_cause_confidence.value,post_repair_result:form.elements.post_repair_result.value,dtc_after_repair:form.elements.dtc_after_repair.value,technician_notes:form.elements.technician_notes.value});form.querySelectorAll('input,textarea,select,button:not(.dialog-close)').forEach(field=>field.disabled=true);node.querySelector('.workspace-message').style.color='inherit';node.querySelector('.workspace-message').textContent=result.contribution?'Merci. Une version anonymisée de ce diagnostic a été envoyée dans la file de revue ORVECT.':'Diagnostic terminé.'}catch(error){submit.disabled=false;failure(node,error)}};
  }

  async function showReview() {
    await authenticated(); const data=await service.request('/admin/review'); const node=dialog('File de revue administrateur', `<p>Contributions anonymisées et suggestions DTC en attente de décision humaine.</p><div class="review-list"></div>`); const list=node.querySelector('.review-list');
    const items=[...data.contributions.map(item=>({kind:'contribution',item})),...data.dtc_submissions.map(item=>({kind:'dtc',item}))];
    if(!items.length){list.innerHTML='<p class="muted">La file de revue est vide.</p>';return}
    for(const entry of items){const card=document.createElement('article');card.className='review-card';card.innerHTML=`<p class="eyebrow">${entry.kind==='dtc'?'Suggestion DTC':'Cas atelier'} · ${escape(entry.item.status)}</p><pre>${escape(JSON.stringify(entry.kind==='dtc'?{code:entry.item.code,manufacturer:entry.item.manufacturer,description:entry.item.description}:entry.item.sanitized_payload,null,2))}</pre>`;list.append(card)}
  }

  const completion=document.createElement('button'); completion.id='completeDiagnostic'; completion.type='button'; completion.className='button dark'; completion.textContent='Diagnostic terminé'; document.querySelector('[data-screen="4"] .button-row').append(completion);
  completion.onclick=()=>showCompletion().catch(error=>{const node=document.querySelector('#diagnosticNotice');node.textContent=error.message;node.classList.add('show','error')});
  function runWorkspaceAction(key) {
    const run = {dashboard:showDashboard,new:()=>window.ORVECT_UI.show(1),active:()=>showHistory(true),history:()=>showHistory(false),knowledge:showKnowledge,suggest:showSuggestion,account:showSettings,review:showReview}[key];
    if (!run) return;
    Promise.resolve().then(run).catch(error=>{if(error.code!=='AUTH_CANCELLED')dialog('Action indisponible',`<p>${escape(error.message)}</p>`)});
  }
  nav.onclick=event=>{const key=event.target.dataset.workspace;if(key)runWorkspaceAction(key)};
  window.ORVECT_WORKSPACE = {
    closeAccount,
    openAccount: () => showSettings().catch(error => {if(error.code!=='AUTH_CANCELLED')dialog('Action indisponible', `<p>${escape(error.message)}</p>`)})
  };
})();
