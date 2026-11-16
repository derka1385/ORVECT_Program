# Connexion sans mot de passe : code par e-mail et QR code

Un seul compte ORVECT relie le site, le téléphone et ORVECT pour Mac.

- **Code par e-mail** : `POST /api/auth/email/start` envoie un code à 6 chiffres (valable 10 minutes, usage unique, 5 essais au plus). Ensuite, `POST /api/auth/email/verify` ouvre la session.
- **QR code** : le Mac appelle `POST /api/auth/device/start` et affiche un QR code qui pointe vers `connexion.html?code=ABCD-EFGH`. Sur le téléphone, on se connecte par code e-mail, puis on autorise le Mac (`POST /api/auth/device/{code}/approve`). Le Mac interroge `POST /api/auth/device/token` toutes les 3 secondes et reçoit sa propre session.

En mode Firebase, la session est un *custom token* Firebase, que le client échange contre sa propre session Firebase. En mode legacy, c'est un jeton d'API. Les codes ne sont stockés que sous forme hachée.

## Mise en production

1. **Migration** : `alembic upgrade head` crée les tables `login_codes` et `device_authorizations` (révision 0015).
2. **Envoi des e-mails depuis `@orvect.fr`** : le domaine est chez IONOS, qui le signe déjà : MX `mx00/mx01.ionos.fr`, SPF `include:_spf-eu.ionos.com`, DKIM `s1-ionos`/`s2-ionos`, DMARC. Aucun enregistrement DNS n'est à ajouter. Il faut :
   - créer dans IONOS la boîte `connexion@orvect.fr` (ou `noreply@`) ;
   - définir sur Render `EMAIL_PROVIDER=smtp`, `SMTP_USERNAME=connexion@orvect.fr`, `SMTP_PASSWORD=<mot de passe de la boîte>` et `EMAIL_FROM="ORVECT <connexion@orvect.fr>"` (`SMTP_HOST=smtp.ionos.fr` et `SMTP_PORT=587` sont les valeurs par défaut).

   Sans ces réglages, la production refuse d'envoyer des codes (erreur 503). En développement, les codes sont seulement écrits dans le journal du serveur. Resend reste possible (`EMAIL_PROVIDER=resend`) si les volumes dépassent les limites d'une boîte IONOS.
3. **Firebase** : pour remettre une session à un appareil, le serveur fabrique un *custom token* signé par un compte de service Firebase.
   - Si Render a déjà `GOOGLE_APPLICATION_CREDENTIALS`, qui pointe vers le JSON du compte de service (voir `firebase-authentication.md`), il n'y a rien à faire : la clé privée qu'il contient suffit pour signer.
   - Si le serveur tourne sans clé (`FIREBASE_CHECK_REVOKED=false`, sans JSON), il faut en créer une : console Firebase › Paramètres du projet › Comptes de service › « Générer une nouvelle clé privée ». Déposer ensuite le fichier comme *Secret File* sur Render, et pointer `GOOGLE_APPLICATION_CREDENTIALS` vers lui. Cette clé ne doit jamais être commitée.
   - Sans clé, le serveur répond « La connexion sans mot de passe n'est pas encore configurée sur ce serveur ».
4. **Page de connexion sur `app.orvect.fr`** : `connexion.html` est publiée avec le site de l'app. GitHub Pages n'accepte qu'un domaine par dépôt, donc tout le site de l'app passe sous `app.orvect.fr` ; `orvect.fr` (la landing) ne change pas. Ordre à suivre :
   1. Dans IONOS, ajouter un enregistrement CNAME `app` → `derka1385.github.io`.
   2. Sur Render, ajouter `https://app.orvect.fr` à `CORS_ORIGINS`, en gardant l'origine `github.io`. Sans ça, l'espace en ligne ne peut plus joindre l'API une fois déplacé.
   3. Dans la console Firebase › Authentication › Paramètres › Domaines autorisés, ajouter `app.orvect.fr`.
   4. Dans GitHub › dépôt `ORVECT_Program` › Settings › Pages, indiquer le domaine personnalisé `app.orvect.fr`, puis cocher « Enforce HTTPS » une fois le certificat émis.

   Les anciennes adresses `derka1385.github.io/ORVECT_Program/…` redirigent alors vers `app.orvect.fr`. `DEVICE_VERIFICATION_URL` peut ensuite passer à `https://app.orvect.fr/connexion.html`.
5. **Nouveaux comptes** : une adresse inconnue n'obtient pas de session tant que `FIREBASE_SELF_SIGNUP_ENABLED` est désactivé.

Tests : `pytest app/tests/test_account_link.py`.
