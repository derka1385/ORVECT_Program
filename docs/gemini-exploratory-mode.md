# Mode exploratoire Gemini

Le réglage serveur `DIAGNOSTIC_EXPLORATION_ENABLED=true`, associé à `LLM_PROVIDER=gemini`, autorise le raisonnement au-delà du catalogue. Il est activé sur le backend HTTPS officiel ; la valeur par défaut du code reste `false`.

Pour un code sans définition documentée, Gemini peut proposer une signification provisoire étiquetée « Approximation Gemini non vérifiée ». Il peut également laisser la définition indisponible et explorer des pistes à partir des symptômes. Toutes les hypothèses, corrélations et propositions de contrôle du mode sont non vérifiées. Les définitions documentées restent identiques à celles du resolver ; aucune source constructeur n’est fabriquée. Le modèle de raisonnement configuré est utilisé, y compris pour un code unique.

Un code seul ne prouve pas une panne. La configuration du véhicule et les codes doivent rester confirmés, et le dossier doit contenir des symptômes ou des observations. La syntaxe des codes et les namespaces restent validés. Les règles de sécurité déterministes et la validation des résultats demeurent actives. Aucun test fini ne peut garantir une réponse correcte pour tous les codes existants.

## Test local reproductible

L’application complète doit fonctionner sur `http://127.0.0.1:3000`. La commande suivante crée cinq dossiers synthétiques persistants, réalise de vrais appels Gemini (potentiellement payants) et teste une réévaluation :

```sh
python3 scripts/verify_exploratory_gemini.py
```

Le rapport est écrit dans `.local/exploratory-gemini-report.json` : codes testés, URL locale, modèle réel enregistré, interprétations, hypothèses, prochaines vérifications, durée et résultat. Les tests couvrent P0171, P1351, U0100, P1FFF volontairement non documenté et P0301 + P0351. Une observation complémentaire du connecteur sert à tester la réévaluation.

## Déploiement officiel

GitHub Pages sert l’interface officielle et appelle `https://orvect-api.onrender.com/api` en HTTPS avec un jeton Bearer obtenu par `/auth/login`. Le backend FastAPI s’exécute sur Render, PostgreSQL sur Neon, et la clé Gemini reste exclusivement dans les variables secrètes Render. L’accès anonyme et les mots de passe de démonstration sont désactivés en production. Ne jamais publier la clé API dans GitHub, le JavaScript ou l’URL.

Le frontend Next.js complet conserve son proxy same-origin `/backend-api`. La page officielle statique utilise `runtime-config.js`, qui ne contient que l’URL publique de l’API et l’identifiant du véhicule synthétique. Les paramètres de production et les prérequis d’authentification sont documentés dans `.env.example` et `docs/security.md`.
