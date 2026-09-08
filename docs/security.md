# Sécurité et sûreté

- **Hallucination IA** : contexte limité, schéma strict, sources obligatoires, moteur de règles souverain et journal des échecs.
- **Mauvaises données** : provenance, checksum, revue humaine, statut de source et indicateur de démonstration.
- **Procédures dangereuses** : avertissements visibles, confirmation humaine à chaque test, aucune écriture ECU ni action distante.
- **Fichiers** : limite globale du corps HTTP, quotas par image/dossier, MIME et contenu contrôlés, limite de pixels avant décodage et rejet des decompression bombs.
- **Multi-tenant** : session opaque hashée, appartenance active et rôle vérifiés côté serveur ; le garage ne vient jamais d’un en-tête client. Le frontend Next passe par le proxy same-origin `/backend-api`. La page GitHub Pages officielle utilise le jeton Bearer opaque uniquement en mémoire et n’enregistre ni jeton ni mot de passe dans le stockage du navigateur.
- **Données client** : VIN et plaque chiffrés, empreinte HMAC stable, suffixes minimaux pour affichage, absence d’identifiants dans le contexte LLM et suppression en cascade du dossier véhicule.
- **Prise en main distante** : hors périmètre ; aucune commande véhicule, suppression de DTC ou codage ECU.

En production, `APP_ENVIRONMENT=production`, `VIN_ENCRYPTION_KEY`, `VIN_FINGERPRINT_SECRET` et un `DEVELOPMENT_SECRET` remplacé sont obligatoires ; les mots de passe de démonstration doivent être vides. Le démarrage échoue explicitement sinon.

Le rate limiting est encore en mémoire et nécessite un stockage partagé avant plusieurs instances. Le mécanisme minimal doit être complété par MFA/SSO, récupération de compte, rotation/révocation centralisée et sélection sécurisée d’un garage pour les utilisateurs multi-garages. CORS est limité par configuration. Une revue OWASP, sauvegardes, rotation opérationnelle des secrets et tests d’intrusion restent requis avant usage réel.
