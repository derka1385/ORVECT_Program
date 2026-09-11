/* Firebase owns credentials and session refresh. ORVECT only receives ID tokens. */
(() => {
  let sdkPromise;
  let pending;
  let mode = 'login';
  let lastFocus;
  const runtime = window.ORVECT_RUNTIME || {};
  const languages = ['fr', 'en', 'sv', 'de'];

  const accountLabel = user => {
    const language = document.documentElement.lang;
    if (user && !user.emailVerified) return ({ fr:'Vérifier le compte', en:'Verify account', sv:'Verifiera kontot', de:'Konto bestätigen' }[language] || 'Vérifier le compte');
    if (user) return ({ fr:'Mon compte', en:'My account', sv:'Mitt konto', de:'Mein Konto' }[language] || 'Mon compte');
    return ({ fr:'Accès au compte', en:'Account access', sv:'Till kontot', de:'Zum Konto' }[language] || 'Accès au compte');
  };

  const account = document.createElement('button');
  account.className = 'account-access'; account.type = 'button';
  account.innerHTML = '<span class="account-access-icon" aria-hidden="true"></span><span data-account-label>Accès au compte</span>';
  (document.querySelector('[data-account-slot]') || document.querySelector('main')).prepend(account);

  function updateAccount(user) {
    const label = accountLabel(user);
    account.querySelector('[data-account-label]').textContent = label;
    account.setAttribute('aria-label', label);
  }

  const style = document.createElement('style');
  style.textContent = `
    body.auth-open{overflow:hidden}
    .auth-page{position:fixed;inset:0;z-index:100;display:grid;grid-template-columns:minmax(390px,.9fr) minmax(520px,1.1fr);overflow:auto;background:var(--mineral);color:var(--graphite)}
    .auth-brand{position:relative;isolation:isolate;display:flex;min-height:100vh;overflow:hidden;flex-direction:column;background:var(--graphite);color:var(--mineral);padding:34px 46px}
    .auth-brand::before{content:"";position:absolute;z-index:-1;right:-165px;bottom:115px;width:430px;height:430px;border:1px solid #ffffff24;transform:rotate(45deg)}
    .auth-brand::after{content:"";position:absolute;z-index:-1;right:68px;bottom:72px;width:92px;height:220px;background:var(--orange);transform:skewY(-18deg)}
    .auth-brand-head{display:flex;align-items:center;justify-content:space-between;gap:18px}.auth-back{flex:0 0 auto;min-height:40px;border:1px solid #ffffff4f;background:transparent;color:var(--mineral);padding:8px 12px;font-size:12px;font-weight:650}.auth-wordmark{font-size:16px;font-weight:700;letter-spacing:-.035em}
    .auth-brand-copy{max-width:570px;margin:auto 0}.auth-brand-copy .eyebrow{color:var(--orange)}.auth-brand-copy h2{max-width:560px;margin:18px 0;font-size:clamp(46px,5vw,74px);line-height:.98;letter-spacing:-.055em}.auth-brand-copy p:last-child{max-width:510px;color:var(--alloy);font-size:17px;line-height:1.55}
    .auth-security-note{position:relative;z-index:1;max-width:370px;border:1px solid #ffffff3b;padding:16px 18px}.auth-security-note strong{display:block;color:var(--orange);font-size:10px;letter-spacing:.08em;text-transform:uppercase}.auth-security-note span{display:block;margin-top:7px;color:var(--alloy);font-size:12px;line-height:1.45}
    .auth-panel{display:grid;min-height:100vh;place-items:center;padding:54px 8vw}.auth-card{width:min(100%,520px)}.auth-card>.eyebrow{color:var(--orange)}.auth-card h1{margin:17px 0 11px;font-size:clamp(38px,4vw,55px);line-height:1;letter-spacing:-.05em}.auth-intro{margin:0;color:var(--muted);font-size:16px;line-height:1.5}
    .auth-tabs{display:grid;grid-template-columns:1fr 1fr;margin-top:34px;border:1px solid var(--line)}.auth-tabs button{min-height:52px;border:0;background:transparent;color:var(--muted);font-weight:650}.auth-tabs button+button{border-left:1px solid var(--line)}.auth-tabs button.active{background:var(--graphite);color:var(--mineral)}
    .auth-form{margin-top:25px}.auth-form label{margin-top:17px}.auth-form .field-label{margin:0 0 8px}.auth-form input{min-height:56px;background:#fff;border-color:var(--line)}.auth-submit{width:100%;min-height:54px;margin-top:24px}
    .auth-link{min-height:42px;margin-top:12px;border:0;background:transparent;padding:7px 0;color:var(--graphite);font-size:13px;font-weight:650;text-decoration:underline;text-underline-offset:4px}
    .auth-message{min-height:24px;margin:18px 0 0;color:var(--danger);font-size:13px;line-height:1.45}.auth-caption{margin-top:20px;color:var(--muted);font-size:11px;line-height:1.5}
    .auth-verify{margin-top:30px;border-top:1px solid var(--line);padding-top:26px}.auth-verify h2{margin:0;font-size:28px}.auth-verify p{color:var(--muted);line-height:1.5}.auth-verify-actions{display:flex;gap:10px;flex-wrap:wrap}.auth-verify-actions .button{min-height:50px}
    @media(max-width:900px){.auth-page{grid-template-columns:1fr}.auth-brand{min-height:270px;padding:20px}.auth-brand-head{align-items:flex-start}.auth-wordmark{max-width:190px;font-size:13px}.auth-back{min-height:34px;padding:6px 8px;font-size:10px}.auth-brand-copy{margin:auto 0 20px}.auth-brand-copy h2{margin:10px 0 0;max-width:330px;font-size:34px}.auth-brand-copy p:last-child,.auth-security-note{display:none}.auth-brand::before{right:-90px;bottom:-180px;width:330px;height:330px}.auth-brand::after{right:45px;bottom:-38px;width:50px;height:130px}.auth-panel{min-height:auto;place-items:start center;padding:38px 20px 64px}.auth-card h1{font-size:41px}.auth-tabs{margin-top:28px}}
  `;
  document.head.append(style);

  const page = document.createElement('section');
  page.className = 'auth-page'; page.hidden = true; page.setAttribute('aria-labelledby', 'firebase-title');
  page.innerHTML = `
    <aside class="auth-brand">
      <div class="auth-brand-head"><div class="auth-wordmark">ORVECT / PROTOTYPE TECHNIQUE</div><button class="auth-back" type="button" data-action="close">← Retour au diagnostic</button></div>
      <div class="auth-brand-copy"><p class="eyebrow">Espace atelier sécurisé</p><h2>Un diagnostic clair commence par un espace protégé.</h2><p>Retrouvez vos dossiers, vos préférences et vos contributions dans un environnement lié à votre garage.</p></div>
      <div class="auth-security-note"><strong>Firebase Authentication</strong><span>Identifiants gérés par Firebase. ORVECT ne stocke jamais votre mot de passe.</span></div>
    </aside>
    <main class="auth-panel">
      <section class="auth-card">
        <p class="eyebrow">Compte ORVECT</p>
        <h1 id="firebase-title">Connexion à ORVECT.</h1>
        <p class="auth-intro" data-auth-intro>Retrouvez vos diagnostics et votre espace atelier.</p>
        <div class="auth-tabs" data-auth-tabs><button class="active" type="button" data-mode="login">Connexion</button><button type="button" data-mode="signup">Inscription</button></div>
        <form class="auth-form" id="firebase-form">
          <label><span class="field-label">E-mail</span><input name="email" type="email" autocomplete="username" required></label>
          <label data-password-field><span class="field-label">Mot de passe</span><input name="password" type="password" autocomplete="current-password" required></label>
          <button class="button primary auth-submit" type="submit" data-submit>Se connecter</button>
        </form>
        <button class="auth-link" type="button" data-action="reset-mode">Mot de passe oublié ?</button>
        <button class="auth-link" type="button" data-action="login-mode" hidden>Retour à la connexion</button>
        <section class="auth-verify" data-verify hidden><h2>Vérifiez votre e-mail.</h2><p>Nous avons envoyé un lien de vérification. Ouvrez-le, puis revenez ici pour terminer la connexion.</p><div class="auth-verify-actions"><button class="button primary" type="button" data-action="refresh">J’ai vérifié mon e-mail</button><button class="button" type="button" data-action="verify">Renvoyer le lien</button></div></section>
        <p class="auth-message" role="status" id="firebase-message"></p>
        <p class="auth-caption">Connexion sécurisée par Firebase. L’accès aux dossiers dépend de votre garage.</p>
      </section>
    </main>`;
  document.body.append(page);

  const form = page.querySelector('#firebase-form');
  const message = page.querySelector('#firebase-message');
  const title = page.querySelector('#firebase-title');
  const intro = page.querySelector('[data-auth-intro]');
  const tabs = page.querySelector('[data-auth-tabs]');
  const passwordField = page.querySelector('[data-password-field]');
  const submit = page.querySelector('[data-submit]');
  const resetLink = page.querySelector('[data-action="reset-mode"]');
  const loginLink = page.querySelector('[data-action="login-mode"]');
  const verifyPanel = page.querySelector('[data-verify]');

  async function sdk() {
    if (!sdkPromise) sdkPromise = (async () => {
      if (location.protocol === 'file:') throw Error('Ouvrez ORVECT via son site HTTPS ou localhost pour vous connecter.');
      if (!runtime.firebase?.apiKey || !runtime.firebase?.projectId || !runtime.firebase?.authDomain) throw Error('La configuration du projet Firebase doit encore être renseignée.');
      const [app, auth] = await Promise.all([
        import('https://www.gstatic.com/firebasejs/12.2.1/firebase-app.js'),
        import('https://www.gstatic.com/firebasejs/12.2.1/firebase-auth.js')
      ]);
      const session = auth.getAuth(app.initializeApp(runtime.firebase));
      session.languageCode = languages.includes(document.documentElement.lang) ? document.documentElement.lang : 'fr';
      await auth.setPersistence(session, auth.browserSessionPersistence);
      await session.authStateReady();
      auth.onAuthStateChanged(session, user => {
        updateAccount(user);
        window.dispatchEvent(new CustomEvent('orvect:auth', { detail: { user } }));
      });
      return { ...auth, session };
    })().catch(error => { sdkPromise = null; throw error; });
    return sdkPromise;
  }

  function errorMessage(error) {
    const messages = {
      'auth/invalid-credential': 'E-mail ou mot de passe incorrect.',
      'auth/weak-password': 'Choisissez un mot de passe d’au moins six caractères.',
      'auth/password-does-not-meet-requirements': 'Choisissez un mot de passe d’au moins six caractères.',
      'auth/admin-restricted-operation': 'La création de compte est temporairement désactivée.',
      'auth/email-already-in-use': 'Ce compte existe déjà. Connectez-vous ou réinitialisez le mot de passe.',
      'auth/too-many-requests': 'Trop de tentatives. Réessayez dans quelques minutes.',
      'auth/network-request-failed': 'Connexion réseau indisponible. Réessayez.',
      'auth/operation-not-allowed': 'Activez la connexion e-mail et mot de passe dans Firebase.'
    };
    return messages[error.code] || (error.code ? 'Connexion impossible. Réessayez.' : error.message);
  }

  function setMode(next) {
    mode = next; message.textContent = ''; message.style.color = ''; form.reset();
    const login = mode === 'login', signup = mode === 'signup', reset = mode === 'reset', verify = mode === 'verify';
    tabs.hidden = reset || verify; form.hidden = verify; passwordField.hidden = reset; verifyPanel.hidden = !verify;
    resetLink.hidden = !login; loginLink.hidden = login || verify;
    page.querySelectorAll('[data-mode]').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
    title.textContent = login ? 'Connexion à ORVECT.' : signup ? 'Créer votre compte ORVECT.' : reset ? 'Réinitialiser le mot de passe.' : 'Vérifiez votre e-mail.';
    intro.textContent = login ? 'Retrouvez vos diagnostics et votre espace atelier.' : signup ? 'Première visite ? Créez votre accès en quelques secondes.' : reset ? 'Indiquez votre e-mail pour recevoir un lien sécurisé.' : 'Votre compte sera accessible après vérification de l’adresse e-mail.';
    submit.textContent = login ? 'Se connecter' : signup ? 'Créer mon compte' : 'Envoyer le lien';
    form.elements.password.autocomplete = signup ? 'new-password' : 'current-password';
    form.elements.password.minLength = signup ? 6 : 0;
    form.elements.password.required = !reset;
    form.elements.password.disabled = reset;
    if (!page.hidden) setTimeout(() => form.elements.email.focus(), 0);
  }

  function openPage(next = 'login') {
    lastFocus = document.activeElement; page.hidden = false; document.body.classList.add('auth-open'); setMode(next);
  }

  function closePage(rejectPending = true) {
    page.hidden = true; document.body.classList.remove('auth-open'); form.reset(); message.textContent = '';
    if (rejectPending && pending) { const error = Error('Connexion annulée.'); error.code = 'AUTH_CANCELLED'; pending.reject(error); pending = null; }
    if (lastFocus instanceof HTMLElement) lastFocus.focus();
  }

  function finish() {
    closePage(false);
    if (pending) { pending.resolve(); pending = null; }
  }

  function busy(active) { page.querySelectorAll('button,input').forEach(control => control.disabled = active); }

  async function authenticate() {
    if (!form.reportValidity()) return;
    busy(true); message.textContent = '';
    try {
      const api = await sdk();
      const email = form.elements.email.value.trim(); const password = form.elements.password.value;
      if (mode === 'reset') {
        await api.sendPasswordResetEmail(api.session, email);
        setMode('login'); form.elements.email.value = email;
        message.style.color = 'inherit'; message.textContent = 'Si ce compte existe, vous recevrez un lien de réinitialisation.'; return;
      }
      if (mode === 'signup') {
        await api.createUserWithEmailAndPassword(api.session, email, password);
        await api.sendEmailVerification(api.session.currentUser);
        setMode('verify'); message.style.color = 'inherit'; message.textContent = 'E-mail de vérification envoyé.'; return;
      }
      await api.signInWithEmailAndPassword(api.session, email, password);
      await api.reload(api.session.currentUser);
      if (!api.session.currentUser.emailVerified) { setMode('verify'); message.textContent = 'Votre e-mail n’est pas encore vérifié.'; return; }
      await api.session.currentUser.getIdToken(true); finish();
    } catch (error) { message.style.color = ''; message.textContent = errorMessage(error); }
    finally { busy(false); }
  }

  async function verificationAction(kind) {
    busy(true); message.textContent = '';
    try {
      const api = await sdk(); const user = api.session.currentUser;
      if (!user) { setMode('login'); throw Error('Connectez-vous pour continuer.'); }
      if (kind === 'verify') { await api.sendEmailVerification(user); message.style.color = 'inherit'; message.textContent = 'E-mail de vérification envoyé.'; return; }
      await api.reload(user);
      if (!user.emailVerified) { message.textContent = 'Votre e-mail n’est pas encore vérifié.'; return; }
      await user.getIdToken(true); finish();
    } catch (error) { message.style.color = ''; message.textContent = errorMessage(error); }
    finally { busy(false); }
  }

  form.onsubmit = event => { event.preventDefault(); authenticate(); };
  page.querySelectorAll('[data-mode]').forEach(button => button.onclick = () => setMode(button.dataset.mode));
  page.querySelector('[data-action="reset-mode"]').onclick = () => setMode('reset');
  page.querySelector('[data-action="login-mode"]').onclick = () => setMode('login');
  page.querySelector('[data-action="verify"]').onclick = () => verificationAction('verify');
  page.querySelector('[data-action="refresh"]').onclick = () => verificationAction('refresh');
  page.querySelector('[data-action="close"]').onclick = () => closePage();
  page.addEventListener('keydown', event => { if (event.key === 'Escape') closePage(); });
  account.onclick = () => {
    if (window.ORVECT_WORKSPACE?.openAccount) { window.ORVECT_WORKSPACE.openAccount(); return; }
    openPage('login');
  };

  window.ORVECT_AUTH = {
    async ensure() {
      const api = await sdk();
      if (api.session.currentUser?.emailVerified) return;
      if (pending) return pending.promise;
      const promise = new Promise((resolve, reject) => { pending = { resolve, reject }; });
      pending.promise = promise;
      openPage(api.session.currentUser ? 'verify' : 'login');
      return promise;
    },
    async token() {
      const api = await sdk();
      if (!api.session.currentUser) throw Error('Connectez-vous pour continuer.');
      return api.session.currentUser.getIdToken();
    },
    async currentUser() { const api = await sdk(); return api.session.currentUser; },
    async resetPassword() {
      const api = await sdk(); const email = api.session.currentUser?.email;
      if (!email) throw Error('Connectez-vous pour continuer.');
      await api.sendPasswordResetEmail(api.session, email);
      return 'Un e-mail de réinitialisation du mot de passe vient d’être envoyé.';
    },
    async logout() { const api = await sdk(); await api.signOut(api.session); location.reload(); },
    open: () => openPage('login')
  };

  window.addEventListener('orvect:language', event => {
    const language = event.detail?.language;
    if (!languages.includes(language)) return;
    sdk().then(({ session }) => { session.languageCode = language; updateAccount(session.currentUser); }).catch(() => {});
  });
  if (runtime.firebase?.apiKey) sdk().catch(error => { message.textContent = errorMessage(error); });
})();
