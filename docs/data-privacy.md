# Confidentialité VIN

Le VIN est chiffré avec Fernet au repos. La déduplication emploie HMAC-SHA-256 avec une clé distincte. Les réponses montrent seulement les six derniers caractères; événements et contexte LLM ne contiennent jamais le VIN.

Configurer `VIN_ENCRYPTION_KEY`, `VIN_FINGERPRINT_SECRET`, `VIN_RETENTION_DAYS` et la limite de débit. Sans clés persistantes, le mode démonstration utilise des clés éphémères et les anciens VIN ne sont plus déchiffrables après redémarrage.

L’isolation se fait par `garage_id`. L’exploitation doit supprimer ou anonymiser les résolutions à l’expiration, invalider le cache sur demande et renouveler les clés selon sa politique.
