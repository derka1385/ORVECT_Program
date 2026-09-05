# Architecture

DiagPilot est un monolithe modulaire : un déploiement backend, une base relationnelle et un frontend Next.js. Les modules `vehicles`, `obd`, `knowledge`, `diagnostics`, `ai`, `garages`, `reports` et `imports` partagent une transaction SQLAlchemy mais gardent leurs contrats et services.

Le flux est : entrée validée → normalisation → Diagnostic Data Resolver → recherche des connaissances sourcées → Diagnostic Engine → LLM Explanation Layer → Safety Engine déterministe → validation et persistance. Une réponse IA invalide est journalisée mais ne devient jamais un diagnostic.

```text
véhicule + ECU + namespace + code --> Diagnostic Data Resolver --> définition / candidats / manque
                                                           |
preuves + définition résolue --------------------> Diagnostic Engine --> hypothèses / insuffisance
                                                                    |
                                                                    +--> LLM Explanation Layer
preuves critiques ------------------------------------------------------> Safety Engine --> UNKNOWN ou règle
session authentifiée --> membership --> garage actif --> filtres de toutes les requêtes
```

Le LLM n’a pas de champ pour décider du danger, de la possibilité de rouler, d’un remplacement ou d’une confirmation définitive. Le `Safety Engine` est exécuté côté serveur après l’analyse et renvoie `UNKNOWN / HUMAN REVIEW` lorsqu’aucune règle fiable ne correspond. Les résultats `inconclusive`, `unavailable`, `invalid` et `refused` sont conservés dans le dossier sans modifier les probabilités.

SQLite facilite le développement local ; PostgreSQL est utilisé dans Compose. L’authentification crée une session opaque dont seul le hash est stocké. Le garage actif est dérivé d’une appartenance active côté serveur ; les identifiants de locataire venant du client ne sont jamais considérés comme une preuve d’accès.

## Décisions

- UUID partout pour éviter les identifiants séquentiels exposés.
- JSON uniquement pour les structures variables (mesures, preuves et règles), relationnel pour les entités et appartenances.
- Corpus versionnés et hachés ; les variantes OEM passent obligatoirement par quarantaine, rapprochement source, vérification humaine et promotion de production.
- Aucun LLM n’est requis pour choisir une procédure ou une branche.
- Toute provenance persistée conserve source, type, version, compatibilité véhicule et horodatage ; sans source vérifiée, le contenu reste `unverified`.
- VIN chiffré pour restitution autorisée, empreinte HMAC stable pour la recherche et suffixe séparé pour l’affichage ; les clés sont obligatoires en production.
- Journal append-only `diagnostic_events` et journal séparé `ai_calls`.

## Admission des données — Phase 1.6

Les fondations Phase 1.5 sont conservées. La migration `0009` ajoute l’évaluation versionnée des droits (`diagnostic_source_assessments`), les conflits explicites (`diagnostic_data_conflicts`) et l’audit de révocation/restauration (`diagnostic_dataset_events`). Les preuves d’identité, de libellé, de sous-type, d’alias et d’applicabilité sont indépendantes et liées à leur valeur par SHA-256. Les Tiers A/B sont contrôlés à la promotion **et** à la résolution ; le Tier C reste fermé en attendant une observation terrain attestée.

Une révocation invalide aussi les preuves de corroboration. Les imports sont idempotents et ne réactivent jamais un dataset révoqué. Les conflits ouverts provoquent une abstention, sans sélection LLM. Aucun dataset VAG réel n’a été admis pendant cette phase : voir le [bilan](phase-1.6-report.md) et la [procédure d’ingestion](vag-ingestion-runbook.md).
