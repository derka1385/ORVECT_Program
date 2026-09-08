# Démonstration investisseur ORVECT — validation du 7 septembre 2026

## Ouvrir le bon programme

L’application officielle connectée à Gemini est https://derka1385.github.io/ORVECT_Program/.
Internet et une connexion ORVECT sont nécessaires pour une nouvelle analyse Gemini. Le fichier `index.html` reste servi par GitHub Pages, mais envoie désormais les dossiers confirmés à l’API HTTPS officielle.

Sur le Mac de Nolann, le fichier exécutable
`/Users/petrinolann/Coding/automotive-diagnostic-ai/Ouvrir_ORVECT.command`
démarre Docker si nécessaire, attend les services et ouvre l’application.
La clé API reste dans la configuration serveur locale et n’est pas publiée.

## Présentation en trois clics

1. Cliquer sur **Charger l’exemple Golf**.
2. Relire les deux codes et cliquer sur **Confirmer tous les DTC non confirmés**.
3. Cliquer sur **Valider et générer les résultats**.

L’exemple contient une Golf VII 1.4 TSI, CZCA, 2018, 86 420 km, les codes P0301 et P0351,
un ralenti irrégulier et trois relevés simulés. Tout est explicitement synthétique.
Le catalogue est interrogé réellement ; les définitions gardent leurs sources communautaires non vérifiées.
L’exemple ne prouve pas une couverture constructeur VAG professionnelle.

Le résultat propose des pistes non confirmées, les éléments qui les soutiennent et un contrôle guidé.
Le prompt encourage 1 à 3 pistes testables lorsque le dossier le permet ; zéro hypothèse reste possible
si aucune piste n’est défendable ou si le contrôle déterministe bloque le dossier.
La certitude de panne n’est jamais une condition préalable à une hypothèse.

## Résultat enregistré prêt à montrer

http://127.0.0.1:3000/diagnostics/ai/4414bf8c-5256-4e50-9130-acd5a8ffd209

Cet exemple est aussi accessible depuis l’accueil via **Ouvrir le résultat Gemini enregistré**
tant qu’il fait partie des dossiers récents.
Il est enregistré dans PostgreSQL et peut être consulté sans nouvel appel à Gemini.
Docker reste nécessaire, mais la consultation ne dépend pas d’Internet.

Trace vérifiée : fournisseur `gemini`, modèle `gemini-3.5-flash`,
prompt `automotive-v3.1-exploratory`, appel terminé en 20,4 secondes,
sortie normalisée puis validée, deux hypothèses :
- faisceau/connecteur de la bobine du cylindre 1 ;
- défaillance interne de la bobine.

Premier contrôle : inspection visuelle du connecteur et du faisceau.
Les réponses d’un nouvel appel peuvent varier ; le résultat enregistré sert de support stable.

## Montrer l’évolution du raisonnement

Dans un nouveau dossier de démonstration, après le premier contrôle visuel proposé :
choisir un résultat informatif et décrire l’observation synthétique suivante :
« SIMULATION : verrou du connecteur cassé, connecteur partiellement débranché,
aucun remplacement effectué. Contact coupé et moteur refroidi. »
Cliquer sur **Enregistrer et réévaluer**.
N’utiliser ce résultat que si le contrôle proposé concerne effectivement cette inspection.
Sinon, ajouter cette observation comme nouvelle mesure dans **Ajouter une preuve au dossier**.

Un essai API a montré le classement évoluer vers le connecteur après cette observation.
Un résultat `unavailable` a conservé la sortie précédente à l’identique.

## Vérifications réalisées

- Gemini rapide `gemini-3.1-flash-lite` : P0301 seul, deux hypothèses et un contrôle.
- Gemini raisonnement `gemini-3.5-flash` : P0301 + P0351, hypothèses et contrôle.
- Réévaluation après ajout de preuve : sortie actualisée.
- Test indisponible : hypothèses inchangées.
- Parcours navigateur réel : charger, confirmer, analyser et afficher le résultat.
- 119 tests backend réussis ; avertissement de dépréciation httpx/Starlette restant.
- TypeScript et build de production réussis ; frontend et backend Docker reconstruits.
- PostgreSQL, backend, frontend : healthy ; Alembic 0009 (head).

Commandes de reproduction, depuis le dépôt :
```sh
python3 scripts/verify_investor_demo.py
python3 scripts/verify_investor_demo.py --follow-up
python3 scripts/verify_investor_demo.py --single-code
```
Ces commandes créent des dossiers synthétiques persistants et consomment des appels Gemini.

## Correctifs

Le cache tient compte du fournisseur, du modèle et de la version du prompt.
Les anciennes sorties mock ne sont plus prises pour une nouvelle analyse Gemini.
Les raisons d’absence d’hypothèse affichées correspondent au résultat réel.
Les contrôles proposés sont soumis à la frontière du prototype, y compris pour les essais routiers
et l’effacement des codes. Les décisions de sécurité restent déterministes.
Aucune donnée historique n’a été supprimée ; les anciens résultats restent conservés.

## Fichiers de cette modification

- backend/Dockerfile.test
- backend/app/modules/diagnostic_ai/analysis_service.py
- backend/app/modules/diagnostic_ai/providers.py
- backend/app/modules/diagnostic_ai/prompts/automotive_v1.txt
- backend/app/tests/test_diagnostic_ai.py
- frontend/src/app/diagnostics/new/page.tsx
- frontend/src/app/diagnostics/ai/[id]/page.tsx
- frontend/public/demo/golf-misfire.json
- scripts/verify_investor_demo.py
- docs/investor-demo-validation.md
- Ouvrir_ORVECT.command : raccourci local ajouté uniquement dans automotive-diagnostic-ai.

Les fichiers applicatifs ont été synchronisés dans automotive-diagnostic-ai et ORVECT_Program.
