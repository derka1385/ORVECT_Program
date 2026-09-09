# Firebase Authentication rollout

The Pages client now uses Firebase email/password authentication, account creation,
verification emails, password reset, session refresh and sign-out. Passwords are
sent only to Firebase. Existing diagnostics and garage permissions stay in SQL.

## Activation (required before publishing the modified client)

1. Create/select the ORVECT Firebase project and register a Web application.
2. Enable Authentication > Email/Password. Configure password policy and email
   enumeration protection. Add the actual site hostname (including
   `derka1385.github.io` if Pages is used) to authorized domains.
3. Copy the public Web configuration (`apiKey`, `authDomain`, `projectId`, `appId`)
   into `runtime-config.js` under `firebase`. This API key identifies Firebase;
   it is not a Gemini key or a service-account private key.
4. On Render, set `FIREBASE_PROJECT_ID` and `AUTH_PROVIDER=firebase`. By default,
   the Admin SDK also checks revocation and therefore requires a mounted Firebase
   service-account JSON through `GOOGLE_APPLICATION_CREDENTIALS`. A keyless host
   can set `FIREBASE_CHECK_REVOKED=false`: signature, audience, issuer and expiry
   remain validated with Google's public Firebase certificates, while explicit
   revocation takes effect when the short-lived ID token expires.
   For the public demo, set `FIREBASE_SELF_SIGNUP_ENABLED=true`; every verified
   signup receives a separate workspace and synthetic Golf fixture.
   Keep `APP_ENVIRONMENT=production` and `DEMO_ACCESS_WITHOUT_LOGIN=false`.
5. Run `alembic upgrade head` before starting the API. Existing user data is kept.
6. Publish the client after the API is configured. Do not publish with `firebase: null`.

An existing ORVECT account is linked once, by a Firebase-verified email address.
After linking, the immutable Firebase UID identifies that account. A recreated
Firebase account cannot take over an already linked ORVECT user. When self-signup
is enabled, a new account receives an isolated garage and synthetic demo vehicle;
signup never grants access to the shared garage.
Existing passwords do not transfer: create a Firebase account with the same email.

Every request verifies token signature, project, issuer and expiry, then checks
the database membership. With `FIREBASE_CHECK_REVOKED=true`, the Admin SDK also
checks explicit revocation and disabled Firebase status.
Legacy login and development bypass are disabled when AUTH_PROVIDER=firebase.
Firestore is not needed for this migration. Do not enable public database rules.

Validate real signup, verified email, login, reset and logout after configuration.
Test a known authorized user and an unassigned user, then a Gemini analysis.
A local file:// page cannot authenticate: serve it on localhost or HTTPS.
The separate Next.js frontend has not been migrated by this Pages change.

References: https://firebase.google.com/docs/auth/admin/verify-id-tokens
and https://firebase.google.com/docs/auth/web/password-auth
