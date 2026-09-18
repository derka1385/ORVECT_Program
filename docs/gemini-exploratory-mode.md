# Mode exploratoire Gemini

Le réglage serveur `DIAGNOSTIC_EXPLORATION_ENABLED=true`, associé à `LLM_PROVIDER=gemini`, autorise le raisonnement au-delà du catalogue. Il est activé sur le Mac de démonstration ; la valeur par défaut du code reste `false`.

Pour un code sans définition documentée, Gemini peut proposer une signification provisoire étiquetée « Approximation Gemini non vérifiée ». Il peut également laisser la définition indisponible et explorer des pistes à partir des symptômes. Toutes les hypothèses, corrélations et propositions de contrôle du mode sont non vérifiées. Les définitions documentées restent identiques à celles du resolver ; aucune source constructeur n’est fabriquée. Le modèle de raisonnement configuré est utilisé, y compris pour un code unique.

Un code seul ne prouve pas une panne. La configuration du véhicule et les codes doivent rester confirmés, et le dossier doit contenir des symptômes ou des observations. La syntaxe des codes et les namespaces restent validés. Les règles de sécurité déterministes et la validation des résultats demeurent actives. Aucun test fini ne peut garantir une réponse correcte pour tous les codes existants.

## Test local reproductible

L’application complète doit fonctionner sur `http://127.0.0.1:3000`. La commande suivante crée cinq dossiers synthétiques persistants, réalise de vrais appels Gemini (potentiellement payants) et teste une réévaluation :

```sh
python3 scripts/verify_exploratory_gemini.py
```

Le rapport est écrit dans `.local/exploratory-gemini-report.json` : codes testés, URL locale, modèle réel enregistré, interprétations, hypothèses, prochaines vérifications, durée et résultat. Les tests couvrent P0171, P1351, U0100, P1FFF volontairement non documenté et P0301 + P0351. Une observation complémentaire du connecteur sert à tester la réévaluation.

## Accès d’un collègue à distance

GitHub Pages héberge une simulation statique et ne peut pas exécuter ce backend Python. Il faut un hébergement du backend et du frontend, avec la clé Gemini exclusivement côté serveur. Un hébergement public doit utiliser l’authentification existante et un environnement de test dédié, sans accès anonyme au garage local. Ne pas publier la clé API dans GitHub, le JavaScript ou l’URL.

Le frontend appelle `/backend-api` ; configurer `API_INTERNAL_URL` vers l’API du backend hébergé. Activer les deux réglages Gemini côté backend. Les paramètres de production et les prérequis d’authentification sont documentés dans `.env.example` et `docs/security.md`.
