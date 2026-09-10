/* Firebase owns credentials and session refresh. ORVECT only receives ID tokens. */
(() => {
  let sdkPromise;
  let pending;
  const runtime = window.ORVECT_RUNTIME || {};
  const accountLabel = user => {
    const labels = { fr: 'Mon compte', en: 'My account', sv: 'Mitt konto', de: 'Mein Konto' };
    return user ? `${labels[document.documentElement.lang] || labels.fr} · ${user.email}` : ({ fr: 'Se connecter', en: 'Sign in', sv: 'Logga in', de: 'Anmelden' }[document.documentElement.lang] || 'Se connecter');
  };
  async function sdk() {
    if (!sdkPromise) sdkPromise = (async () => {
      if (location.protocol === 'file:') throw Error('Ouvrez ORVECT via son site HTTPS ou localhost pour vous connecter.');
      if (!runtime.firebase?.apiKey || !runtime.firebase?.projectId || !runtime.firebase?.authDomain) {
        throw Error('La configuration du projet Firebase doit encore être renseignée.');
      }
      const [app, auth] = await Promise.all([
        import('https://www.gstatic.com/firebasejs/12.2.1/firebase-app.js'),
        import('https://www.gstatic.com/firebasejs/12.2.1/firebase-auth.js')
      ]);
      const session = auth.getAuth(app.initializeApp(runtime.firebase));
      session.languageCode = ['fr', 'en', 'sv', 'de'].includes(document.documentElement.lang) ? document.documentElement.lang : 'fr';
      await auth.setPersistence(session, auth.browserSessionPersistence);
      await session.authStateReady();
      auth.onAuthStateChanged(session, user => {
        account.textContent = accountLabel(user);
      });
      return { ...auth, session };
    })().catch(error => { sdkPromise = null; throw error; });
    return sdkPromise;
  }
  const dialog = document.createElement('dialog');
  dialog.setAttribute('aria-labelledby', 'firebase-title');
  dialog.style.cssText = 'max-width:440px;width:calc(100% - 32px);padding:24px;border:1px solid #d5d5d2;background:#f5f5f0;color:#171a1b';
  dialog.innerHTML = `<form id="firebase-form">
    <h2 id="firebase-title">Votre compte ORVECT</h2>
    <p>Connexion sécurisée par Firebase. L’accès aux dossiers dépend de votre garage.</p>
    <label>E-mail<input name="email" type="email" autocomplete="username" required></label>
    <label>Mot de passe<input name="password" type="password" autocomplete="current-password" required></label>
    <p role="status" id="firebase-message"></p>
    <div class="button-row"><button class="button primary" type="submit">Se connecter</button>
    <button class="button" type="button" data-action="signup">Créer un compte</button>
    <button class="button" type="button" data-action="reset">Mot de passe oublié</button>
    <button class="button" type="button" data-action="verify">Renvoyer l’e-mail de vérification</button>
    <button class="button" type="button" data-action="refresh">J’ai vérifié mon e-mail</button>
    <button class="button" type="button" data-action="logout">Se déconnecter</button>
    <button class="button" type="button" data-action="close">Fermer</button></div></form>`;
  document.body.append(dialog);
  const form = dialog.querySelector('form');
  const message = dialog.querySelector('#firebase-message');
  const account = document.createElement('button');
  account.className = 'button'; account.textContent = 'Se connecter'; account.type = 'button';
  document.querySelector('main').prepend(account);
  function errorMessage(error) {
    const messages = {
      'auth/invalid-credential': 'E-mail ou mot de passe incorrect.',
      'auth/weak-password': 'Choisissez un mot de passe plus long et plus robuste.',
      'auth/email-already-in-use': 'Ce compte existe déjà. Connectez-vous ou réinitialisez le mot de passe.',
      'auth/too-many-requests': 'Trop de tentatives. Réessayez dans quelques minutes.',
      'auth/network-request-failed': 'Connexion réseau indisponible. Réessayez.',
      'auth/operation-not-allowed': 'Activez la connexion e-mail et mot de passe dans Firebase.',
    };
    return messages[error.code] || (error.code ? 'Connexion impossible. Réessayez.' : error.message);
  }
  function finish() {
    form.reset(); dialog.close();
    if (pending) { pending.resolve(); pending = null; }
  }
  async function action(kind) {
    const buttons = [...dialog.querySelectorAll('button')];
    buttons.forEach(button => button.disabled = true); message.textContent = '';
    try {
      const api = await sdk(); const email = form.elements.email.value.trim(); const password = form.elements.password.value;
      if (['login', 'signup'].includes(kind) && !form.reportValidity()) return;
      if (kind === 'login') await api.signInWithEmailAndPassword(api.session, email, password);
      if (kind === 'signup') {
        await api.createUserWithEmailAndPassword(api.session, email, password);
        await api.sendEmailVerification(api.session.currentUser);
        message.textContent = 'Compte créé. Vérifiez votre e-mail, puis cliquez sur « J’ai vérifié mon e-mail ». Votre espace de démonstration privé sera créé à la première connexion.';
        form.elements.password.value = ''; return;
      }
      if (kind === 'reset') {
        if (!form.elements.email.reportValidity()) return;
        await api.sendPasswordResetEmail(api.session, email);
        message.textContent = 'Si ce compte existe, vous recevrez un lien de réinitialisation.'; return;
      }
      if (kind === 'logout') { await api.signOut(api.session); location.reload(); return; }
      if (kind === 'verify') {
        if (!api.session.currentUser) throw Error('Connectez-vous d’abord pour vérifier votre compte.');
        await api.sendEmailVerification(api.session.currentUser);
        message.textContent = 'E-mail de vérification envoyé.'; return;
      }
      const user = api.session.currentUser;
      if (!user) throw Error('Connectez-vous pour continuer.');
      await api.reload(user);
      if (!user.emailVerified) throw Error('Vérifiez votre adresse e-mail, puis cliquez sur « J’ai vérifié mon e-mail ».');
      await user.getIdToken(true); finish();
    } catch (error) { message.textContent = errorMessage(error); }
    finally { buttons.forEach(button => button.disabled = false); }
  }
  function cancel() {
    form.reset(); dialog.close();
    if (pending) { pending.reject(Error('Connexion annulée.')); pending = null; }
  }
  form.onsubmit = event => { event.preventDefault(); action('login'); };
  dialog.querySelectorAll('[data-action]').forEach(button => button.onclick = () => button.dataset.action === 'close' ? cancel() : action(button.dataset.action));
  dialog.oncancel = event => { event.preventDefault(); cancel(); };
  account.onclick = () => { message.textContent = ''; dialog.showModal(); };
  window.ORVECT_AUTH = {
    async ensure() {
      const api = await sdk();
      if (api.session.currentUser?.emailVerified) return;
      if (pending) return pending.promise;
      const promise = new Promise((resolve, reject) => { pending = { resolve, reject }; });
      pending.promise = promise; message.textContent = ''; if (!dialog.open) dialog.showModal(); return promise;
    },
    async token() {
      const api = await sdk();
      if (!api.session.currentUser) throw Error('Connectez-vous pour continuer.');
      return api.session.currentUser.getIdToken();
    }
  };
  window.addEventListener('orvect:language', event => {
    const language = event.detail?.language;
    if (!['fr', 'en', 'sv', 'de'].includes(language)) return;
    sdk().then(({ session }) => {
      session.languageCode = language;
      account.textContent = accountLabel(session.currentUser);
    }).catch(() => {});
  });
  if (runtime.firebase?.apiKey) sdk().catch(error => { message.textContent = errorMessage(error); });
})();
