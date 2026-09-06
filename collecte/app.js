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

  function downloadJson(data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${data.caseId}-cas-anonyme.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function openMail(data) {
    const vehicle = [data.vehicle.make, data.vehicle.model].filter(Boolean).join(' ') || 'véhicule non précisé';
    const subject = `ORVECT — Cas atelier ${data.caseId} — ${vehicle}`;
    const body = `Bonjour ORVECT,\n\nVeuillez trouver le fichier JSON anonyme du cas ${data.caseId}, téléchargé à l’instant, à joindre à ce message.\n\nVéhicule : ${vehicle}\nDTC : ${data.incident.dtcs.map(item => item.code).join(', ')}\nRésultat : ${data.resolution.outcome}\n\nMerci.`;
    window.location.href = `mailto:derka1385@yahoo.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
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
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!validate()) return;
    lastPayload = payload();
    downloadJson(lastPayload);
    localStorage.removeItem(draftKey);
    const dialog = document.querySelector('#successDialog');
    if (dialog.showModal) dialog.showModal();
    setTimeout(() => openMail(lastPayload), 350);
  });
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => document.querySelector('#successDialog').close()));
  document.querySelector('#copyJson').addEventListener('click', async () => {
    if (!lastPayload) return;
    await navigator.clipboard.writeText(JSON.stringify(lastPayload, null, 2));
    document.querySelector('#copyState').textContent = 'JSON copié dans le presse-papiers.';
  });
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
