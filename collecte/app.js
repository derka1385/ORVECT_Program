(() => {
  const form = document.querySelector('#caseForm');
  const draftKey = 'orvect-workshop-case-draft-v2';
  const dtcs = [];
  let lastPayload = null;
  let saveTimer;

  const clean = value => String(value ?? '').trim();
  const field = name => form.elements.namedItem(name);
  const optionalNumber = name => clean(field(name).value) ? Number(field(name).value) : null;

  function definitionFor(code) {
    const row = window.ORVECT_DTC_CATALOG?.definitions?.[code];
    return row?.[0] || '';
  }

  function renderDtcs() {
    const list = document.querySelector('#dtcList');
    list.innerHTML = dtcs.length ? dtcs.map((item, index) => `
      <article class="dtc-item">
        <code>${item.code}</code>
        <p>${item.meaning || 'Signification non renseignée'}</p>
        <button class="remove-dtc" type="button" data-remove-dtc="${index}" aria-label="Supprimer ${item.code}">×</button>
      </article>`).join('') : '<p class="empty">Aucun code ajouté.</p>';
  }

  function addDtc() {
    const codeInput = document.querySelector('#dtcCode');
    const meaningInput = document.querySelector('#dtcMeaning');
    const error = document.querySelector('#dtcError');
    const code = clean(codeInput.value).toUpperCase().replace(/\s+/g, '');
    error.textContent = '';
    if (!/^[PBCU][0-9A-F]{4}$/.test(code)) {
      error.textContent = 'Saisissez un code OBD valide, par exemple P0299.';
      codeInput.focus();
      return;
    }
    if (dtcs.some(item => item.code === code)) {
      error.textContent = 'Ce code est déjà présent dans le dossier.';
      codeInput.focus();
      return;
    }
    dtcs.push({ code, meaning: clean(meaningInput.value) || definitionFor(code), source: meaningInput.value ? 'technician' : definitionFor(code) ? 'community_catalog_unreviewed' : 'unknown' });
    codeInput.value = '';
    meaningInput.value = '';
    renderDtcs();
    saveDraft();
    codeInput.focus();
  }

  function formValues() {
    return Object.fromEntries([...new FormData(form).entries()].filter(([name]) => name !== 'consent'));
  }

  function saveDraft() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      localStorage.setItem(draftKey, JSON.stringify({ fields: formValues(), dtcs }));
      const state = document.querySelector('#saveState');
      state.textContent = 'Brouillon sauvegardé';
      state.classList.add('saved');
      setTimeout(() => { state.textContent = 'Brouillon local'; state.classList.remove('saved'); }, 1800);
    }, 250);
  }

  function restoreDraft() {
    try {
      const draft = JSON.parse(localStorage.getItem(draftKey));
      if (!draft) return;
      Object.entries(draft.fields || {}).forEach(([name, value]) => { const input = field(name); if (input) input.value = value; });
      dtcs.push(...(Array.isArray(draft.dtcs) ? draft.dtcs : []));
      renderDtcs();
    } catch { localStorage.removeItem(draftKey); }
  }

  function payload() {
    return {
      schema: 'orvect.workshop_case',
      schemaVersion: 2,
      caseId: `ORV-${new Date().toISOString().replace(/\D/g, '').slice(0, 14)}-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
      submittedAt: new Date().toISOString(),
      language: 'fr',
      anonymous: true,
      vehicle: {
        make: clean(field('make').value) || null,
        model: clean(field('model').value) || null,
        firstRegistrationYear: optionalNumber('year'),
        engineCode: clean(field('engineCode').value).toUpperCase() || null,
        gearboxCode: clean(field('gearboxCode').value).toUpperCase() || null,
        power: optionalNumber('power'),
        powerUnit: clean(field('powerUnit').value) || null,
        mileageKm: optionalNumber('mileage'),
        fuel: clean(field('fuel').value) || null,
        gearboxType: clean(field('gearboxType').value) || null
      },
      incident: {
        symptoms: clean(field('symptoms').value),
        occurrenceConditions: clean(field('conditions').value) || null,
        dtcs: dtcs.map(item => ({ ...item })),
        diagnosticSteps: clean(field('diagnosticSteps').value)
      },
      resolution: {
        repairAction: clean(field('repairAction').value),
        rootCause: clean(field('rootCause').value),
        partsReplaced: clean(field('partsReplaced').value) || null,
        outcome: clean(field('outcome').value),
        verification: clean(field('verification').value) || null,
        lessonLearned: clean(field('lessonLearned').value) || null
      },
      consent: { anonymizedTrainingUse: true, personalCustomerDataExcluded: true }
    };
  }

  function validate() {
    form.querySelectorAll('.invalid').forEach(el => el.classList.remove('invalid'));
    const invalid = [...form.querySelectorAll(':invalid')];
    const errors = [];
    invalid.forEach(input => {
      input.classList.add('invalid');
      const label = input.closest('label')?.querySelector(':scope > span')?.textContent.replace('*', '').trim() || 'Champ obligatoire';
      errors.push(label);
    });
    if (!dtcs.length) { errors.push('Au moins un code d’erreur'); document.querySelector('#dtcError').textContent = 'Ajoutez au moins un code d’erreur.'; }
    const summary = document.querySelector('#errorSummary');
    if (errors.length) {
      summary.hidden = false;
      summary.innerHTML = `<strong>Il manque ${errors.length} information${errors.length > 1 ? 's' : ''} :</strong> ${[...new Set(errors)].join(', ')}.`;
      summary.focus();
      (invalid[0] || document.querySelector('#dtcCode')).focus({ preventScroll: true });
      summary.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return false;
    }
    summary.hidden = true;
    return true;
  }

  function caseText(data) {
    const vehicle = [data.vehicle.make, data.vehicle.model].filter(Boolean).join(' ') || 'Non renseigné';
    const value = item => item ?? 'Non renseigné';
    return [
      'ORVECT — CAS ATELIER ANONYME',
      `ID : ${data.caseId}`,
      `Date : ${data.submittedAt}`,
      '',
      'VÉHICULE',
      `Marque / modèle : ${vehicle}`,
      `Année : ${value(data.vehicle.firstRegistrationYear)}`,
      `Code moteur : ${value(data.vehicle.engineCode)}`,
      `Code boîte : ${value(data.vehicle.gearboxCode)}`,
      `Puissance : ${data.vehicle.power ? `${data.vehicle.power} ${data.vehicle.powerUnit}` : 'Non renseignée'}`,
      `Kilométrage : ${data.vehicle.mileageKm ? `${data.vehicle.mileageKm} km` : 'Non renseigné'}`,
      `Carburant : ${value(data.vehicle.fuel)}`,
      `Type de boîte : ${value(data.vehicle.gearboxType)}`,
      '',
      'CODES D’ERREUR',
      ...data.incident.dtcs.map(item => `${item.code} — ${item.meaning || 'Signification non renseignée'}`),
      '',
      'SYMPTÔMES', data.incident.symptoms,
      '',
      'CONDITIONS D’APPARITION', value(data.incident.occurrenceConditions),
      '',
      'CONTRÔLES ET RECHERCHES', data.incident.diagnosticSteps,
      '',
      'INTERVENTION', data.resolution.repairAction,
      '',
      'CAUSE RÉELLE', data.resolution.rootCause,
      '',
      `Pièces remplacées : ${value(data.resolution.partsReplaced)}`,
      `Résultat : ${data.resolution.outcome}`,
      `Vérification : ${value(data.resolution.verification)}`,
      `Information utile : ${value(data.resolution.lessonLearned)}`,
      '',
      'Export anonyme — sans nom, e-mail, plaque ni VIN.'
    ].join('\n');
  }

  function caseFiles(data) {
    const basename = `${data.caseId}-cas-anonyme`;
    return [
      new File([caseText(data)], `${basename}.txt`, { type: 'text/plain;charset=utf-8' }),
      new File([JSON.stringify(data, null, 2)], `${basename}.json`, { type: 'application/json' })
    ];
  }

  function downloadFile(file) {
    const blob = new Blob([file], { type: file.type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = file.name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function openMail(data) {
    const vehicle = [data.vehicle.make, data.vehicle.model].filter(Boolean).join(' ') || 'véhicule non précisé';
    const subject = `ORVECT — Cas atelier ${data.caseId} — ${vehicle}`;
    const body = `Bonjour ORVECT,\n\nVeuillez trouver les fichiers TXT et JSON anonymes du cas ${data.caseId}, téléchargés à l’instant, à joindre à ce message.\n\n${caseText(data)}`;
    window.location.href = `mailto:derka1385@yahoo.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }

  async function shareCase(data) {
    const files = caseFiles(data);
    if (!navigator.canShare?.({ files })) return false;
    try {
      await navigator.share({ title: `Cas atelier ${data.caseId}`, text: 'Cas atelier anonyme ORVECT — TXT + JSON', files });
      return true;
    } catch (error) {
      return error?.name === 'AbortError';
    }
  }

  document.querySelector('#dtcCode').addEventListener('blur', event => {
    const code = clean(event.target.value).toUpperCase();
    const meaning = document.querySelector('#dtcMeaning');
    if (!meaning.value) meaning.value = definitionFor(code);
  });
  document.querySelector('#dtcCode').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); addDtc(); } });
  document.querySelector('#addDtc').addEventListener('click', addDtc);
  document.querySelector('#dtcList').addEventListener('click', event => {
    const button = event.target.closest('[data-remove-dtc]');
    if (!button) return;
    dtcs.splice(Number(button.dataset.removeDtc), 1);
    renderDtcs(); saveDraft();
  });
  form.addEventListener('input', saveDraft);
  form.addEventListener('change', saveDraft);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!validate()) return;
    lastPayload = payload();
    localStorage.removeItem(draftKey);
    const dialog = document.querySelector('#successDialog');
    if (dialog.showModal) dialog.showModal();
    const files = caseFiles(lastPayload);
    const canShareFiles = Boolean(navigator.canShare?.({ files }));
    document.querySelector('#shareCase').hidden = !canShareFiles;
    if (canShareFiles) {
      document.querySelector('#deliveryText').textContent = 'Choisissez Mail ou AirDrop dans le partage iPhone pour envoyer les fichiers TXT et JSON vers votre Mac.';
      await shareCase(lastPayload);
    } else {
      files.forEach(downloadFile);
      document.querySelector('#deliveryText').textContent = 'Les fichiers TXT et JSON ont été téléchargés. Joignez-les au message ORVECT qui vient de s’ouvrir.';
      setTimeout(() => openMail(lastPayload), 350);
    }
  });
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => document.querySelector('#successDialog').close()));
  document.querySelector('#downloadText').addEventListener('click', () => { if (lastPayload) downloadFile(caseFiles(lastPayload)[0]); });
  document.querySelector('#downloadJson').addEventListener('click', () => { if (lastPayload) downloadFile(caseFiles(lastPayload)[1]); });
  document.querySelector('#shareCase').addEventListener('click', async () => { if (lastPayload) await shareCase(lastPayload); });
  document.querySelector('#newCase').addEventListener('click', () => {
    form.reset(); dtcs.splice(0); renderDtcs(); lastPayload = null;
    localStorage.removeItem(draftKey); document.querySelector('#successDialog').close(); window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  const observer = new IntersectionObserver(entries => {
    const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    document.querySelectorAll('[data-progress]').forEach(item => item.classList.toggle('active', item.dataset.progress === visible.target.dataset.section));
  }, { rootMargin: '-25% 0px -55% 0px', threshold: [0, .2, .5] });
  document.querySelectorAll('[data-section]').forEach(section => observer.observe(section));
  restoreDraft();
})();
