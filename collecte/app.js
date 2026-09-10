(() => {
  const form = document.querySelector('#caseForm');
  const draftKey = 'orvect-workshop-case-draft-v2';
  const dtcs = [];
  let lastPayload = null;
  let saveTimer;

  const messages = {
    fr: {
      meaningMissing: 'Signification non renseignée', invalidCode: 'Saisissez un code OBD valide, par exemple P0299.', duplicateCode: 'Ce code est déjà présent dans le dossier.', draftSaved: 'Brouillon sauvegardé', draftLocal: 'Brouillon local', requiredField: 'Champ obligatoire', atLeastOneCode: 'Au moins un code d’erreur', addOneCode: 'Ajoutez au moins un code d’erreur.', missing: count => `Il manque ${count} information${count > 1 ? 's' : ''} :`, iphoneDelivery: 'Choisissez Mail ou AirDrop dans le partage iPhone pour envoyer les fichiers TXT et JSON vers votre Mac.', downloadedDelivery: 'Les fichiers TXT et JSON ont été téléchargés. Joignez-les au message ORVECT qui vient de s’ouvrir.', mailHello: 'Bonjour ORVECT,', mailFiles: id => `Veuillez trouver les fichiers TXT et JSON anonymes du cas ${id}, téléchargés à l’instant, à joindre à ce message.`, vehicleUnknown: 'véhicule non précisé', shareTitle: id => `Cas atelier ${id}`, shareText: 'Cas atelier anonyme ORVECT — TXT + JSON'
    },
    en: {
      meaningMissing: 'Meaning not provided', invalidCode: 'Enter a valid OBD code, for example P0299.', duplicateCode: 'This code is already in the case.', draftSaved: 'Draft saved', draftLocal: 'Local draft', requiredField: 'Required field', atLeastOneCode: 'At least one fault code', addOneCode: 'Add at least one fault code.', missing: count => `${count} required item${count > 1 ? 's are' : ' is'} missing:`, iphoneDelivery: 'Choose Mail or AirDrop in the iPhone share sheet to send the TXT and JSON files to your Mac.', downloadedDelivery: 'The TXT and JSON files were downloaded. Attach them to the ORVECT message that just opened.', mailHello: 'Hello ORVECT,', mailFiles: id => `Please find the anonymous TXT and JSON files for case ${id}, just downloaded and ready to attach to this message.`, vehicleUnknown: 'vehicle not specified', shareTitle: id => `Workshop case ${id}`, shareText: 'Anonymous ORVECT workshop case — TXT + JSON'
    },
    sv: {
      meaningMissing: 'Betydelse ej angiven', invalidCode: 'Ange en giltig OBD-kod, till exempel P0299.', duplicateCode: 'Koden finns redan i ärendet.', draftSaved: 'Utkast sparat', draftLocal: 'Lokalt utkast', requiredField: 'Obligatoriskt fält', atLeastOneCode: 'Minst en felkod', addOneCode: 'Lägg till minst en felkod.', missing: count => `${count} obligatorisk${count > 1 ? 'a uppgifter' : ' uppgift'} saknas:`, iphoneDelivery: 'Välj Mail eller AirDrop i iPhones delningsmeny för att skicka TXT- och JSON-filerna till din Mac.', downloadedDelivery: 'TXT- och JSON-filerna har hämtats. Bifoga dem till ORVECT-meddelandet som nyss öppnades.', mailHello: 'Hej ORVECT,', mailFiles: id => `Här är de anonyma TXT- och JSON-filerna för ärende ${id}, nyss hämtade och redo att bifogas till meddelandet.`, vehicleUnknown: 'fordon ej angivet', shareTitle: id => `Verkstadsärende ${id}`, shareText: 'Anonymt ORVECT-verkstadsärende — TXT + JSON'
    },
    de: {
      meaningMissing: 'Bedeutung nicht angegeben', invalidCode: 'Geben Sie einen gültigen OBD-Code ein, zum Beispiel P0299.', duplicateCode: 'Dieser Code ist bereits im Fall enthalten.', draftSaved: 'Entwurf gespeichert', draftLocal: 'Lokaler Entwurf', requiredField: 'Pflichtfeld', atLeastOneCode: 'Mindestens ein Fehlercode', addOneCode: 'Fügen Sie mindestens einen Fehlercode hinzu.', missing: count => `${count} Pflichtangabe${count > 1 ? 'n fehlen' : ' fehlt'}:`, iphoneDelivery: 'Wählen Sie im iPhone-Teilen-Menü Mail oder AirDrop, um die TXT- und JSON-Dateien an Ihren Mac zu senden.', downloadedDelivery: 'Die TXT- und JSON-Dateien wurden heruntergeladen. Fügen Sie sie der soeben geöffneten ORVECT-Nachricht hinzu.', mailHello: 'Hallo ORVECT,', mailFiles: id => `Anbei die anonymen TXT- und JSON-Dateien für den Fall ${id}, die gerade heruntergeladen wurden und dieser Nachricht beigefügt werden können.`, vehicleUnknown: 'Fahrzeug nicht angegeben', shareTitle: id => `Werkstattfall ${id}`, shareText: 'Anonymer ORVECT-Werkstattfall — TXT + JSON'
    }
  };
  const copy = key => messages[document.documentElement.lang]?.[key] ?? messages.fr[key];

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
        <p>${item.meaning || copy('meaningMissing')}</p>
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
      error.textContent = copy('invalidCode');
      codeInput.focus();
      return;
    }
    if (dtcs.some(item => item.code === code)) {
      error.textContent = copy('duplicateCode');
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
      language: document.documentElement.lang || 'fr',
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
      const label = input.closest('label')?.querySelector(':scope > span')?.textContent.replace('*', '').trim() || copy('requiredField');
      errors.push(label);
    });
    if (!dtcs.length) { errors.push(copy('atLeastOneCode')); document.querySelector('#dtcError').textContent = copy('addOneCode'); }
    const summary = document.querySelector('#errorSummary');
    if (errors.length) {
      summary.hidden = false;
      summary.innerHTML = `<strong>${copy('missing')(errors.length)}</strong> ${[...new Set(errors)].join(', ')}.`;
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
    if (data.language === 'de') {
      const germanVehicle = [data.vehicle.make, data.vehicle.model].filter(Boolean).join(' ') || 'Nicht angegeben';
      const germanValue = item => item ?? 'Nicht angegeben';
      return [
        'ORVECT — ANONYMER WERKSTATTFALL',
        `ID: ${data.caseId}`,
        `Datum: ${data.submittedAt}`,
        '',
        'FAHRZEUG',
        `Marke / Modell: ${germanVehicle}`,
        `Jahr: ${germanValue(data.vehicle.firstRegistrationYear)}`,
        `Motorkennbuchstabe: ${germanValue(data.vehicle.engineCode)}`,
        `Getriebecode: ${germanValue(data.vehicle.gearboxCode)}`,
        `Leistung: ${data.vehicle.power ? `${data.vehicle.power} ${data.vehicle.powerUnit}` : 'Nicht angegeben'}`,
        `Kilometerstand: ${data.vehicle.mileageKm ? `${data.vehicle.mileageKm} km` : 'Nicht angegeben'}`,
        `Kraftstoff: ${germanValue(data.vehicle.fuel)}`,
        `Getriebeart: ${germanValue(data.vehicle.gearboxType)}`,
        '',
        'FEHLERCODES',
        ...data.incident.dtcs.map(item => `${item.code} — ${item.meaning || 'Bedeutung nicht angegeben'}`),
        '',
        'SYMPTOME', data.incident.symptoms,
        '',
        'AUFTRETENSBEDINGUNGEN', germanValue(data.incident.occurrenceConditions),
        '',
        'PRÜFUNGEN UND UNTERSUCHUNGEN', data.incident.diagnosticSteps,
        '',
        'REPARATUR', data.resolution.repairAction,
        '',
        'TATSÄCHLICHE URSACHE', data.resolution.rootCause,
        '',
        `Ersetzte Teile: ${germanValue(data.resolution.partsReplaced)}`,
        `Ergebnis: ${data.resolution.outcome}`,
        `Prüfung: ${germanValue(data.resolution.verification)}`,
        `Nützliche Information: ${germanValue(data.resolution.lessonLearned)}`,
        '',
        'Anonymer Export — ohne Namen, E-Mail-Adresse, Kennzeichen oder FIN.'
      ].join('\n');
    }
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
    const vehicle = [data.vehicle.make, data.vehicle.model].filter(Boolean).join(' ') || copy('vehicleUnknown');
    const subject = `ORVECT — Cas atelier ${data.caseId} — ${vehicle}`;
    const body = `${copy('mailHello')}\n\n${copy('mailFiles')(data.caseId)}\n\n${caseText(data)}`;
    window.location.href = `mailto:derka1385@yahoo.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }

  async function shareCase(data) {
    const files = caseFiles(data);
    if (!navigator.canShare?.({ files })) return false;
    try {
      await navigator.share({ title: copy('shareTitle')(data.caseId), text: copy('shareText'), files });
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
      document.querySelector('#deliveryText').textContent = copy('iphoneDelivery');
      await shareCase(lastPayload);
    } else {
      files.forEach(downloadFile);
      document.querySelector('#deliveryText').textContent = copy('downloadedDelivery');
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
  window.addEventListener('orvect:language', renderDtcs);
  restoreDraft();
})();
