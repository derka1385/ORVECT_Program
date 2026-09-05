# Contrats API

La documentation interactive est disponible sur `/docs` et le schéma OpenAPI sur `/openapi.json`. Toutes les routes métier sont préfixées par `/api`.

Toutes les routes métier exigent une session authentifiée, transmise par cookie `HttpOnly` ou jeton Bearer opaque. Le garage actif provient de la `GarageMembership` vérifiée côté serveur ; un `garage_id` ou un en-tête `X-Garage-ID` fourni par le client est ignoré. Les routes d’import et de gestion de connaissance exigent le rôle `admin`. Les erreurs utilisent le format FastAPI `{"detail": ...}` avec un message exploitable.

Les collections renvoient `{items, page, page_size, total}`. La taille par défaut est 50 et la limite serveur 100.

Le rapport OBD canonique utilise `schema_version: "1.0"`, un objet véhicule et un scan contenant horodatage, outil, DTC, freeze frame et données live. Les modèles Pydantic refusent les champs inconnus. Les fichiers sont limités à 1 Mio et aux formats JSON/CSV.

## Données diagnostic versionnées

- `POST /api/diagnostic-data/resolve` accepte un `namespace`, un identifiant libre de la contrainte `Pxxxx`, un véhicule optionnel, le module et les références ECU. Les états sont `resolved`, `ambiguous`, `insufficient_vehicle_configuration`, `definition_unavailable_for_vehicle_configuration` et `unknown`.
- `POST /api/diagnostic-data/imports` importe un manifeste structuré, haché et légalement attesté. Réservé au rôle `admin`; toutes les lignes commencent en quarantaine.
- `POST /api/diagnostic-data/definitions/{id}/promote` et `/aliases/{id}/promote` appliquent une seule transition contrôlée à la fois.
- `GET /api/diagnostic-data/datasets`, `/definitions` et `/aliases` sont paginés et réservés aux administrateurs.
- `GET /api/diagnostic-data/coverage` expose les ratios documentés par namespace, constructeur, marque, ECU ou type de code.

Une réponse `resolved` contient la référence source minimale immuable utilisée par la couche LLM et `source_details`, qui ajoute licence, éditeur, dataset, version et checksum. Les candidats ambigus conservent chacun leur provenance et ne sont jamais présentés comme définition sélectionnée.

`POST /api/imports/knowledge` accepte le corpus JSON strict décrit dans `data/fixtures/demo_knowledge.json`. Le checksum SHA-256 détecte un contenu déjà importé ; l’écriture de la source et de tous ses items utilise une seule transaction. Ce MVP refuse tout corpus qui ne porte pas `demo_only: true` à tous les niveaux.

Voir les routes et exemples directement dans Swagger, les contrats restant générés depuis les schémas exécutables.

## Admission et révocation — Phase 1.6

Toutes les écritures suivantes exigent `admin` et sont préfixées par `/api/diagnostic-data` :

- `POST /sources/{id}/assessment` : évaluation des droits liée à la version enregistrée, immuable hors révocation ; `POST /sources/{id}/revoke` exige une raison et invalide ses preuves.
- `POST /datasets/{id}/revoke` et `/restore` : retrait/restauration contrôlés, sans suppression de l’historique. Un réimport identique retourne le même dataset sans le réactiver.
- `GET /source-assessments`, `/conflicts` et `/dataset-events` : collections administrateur paginées ; les événements peuvent être filtrés par `dataset_id`.
- `POST /conflicts/{id}/resolve` : justification obligatoire ; aucune promotion implicite.

Le manifeste conserve sa version `1.0` et ajoute les preuves par champ à `provenance`. Une licence déclarée ne suffit plus à l’admission. La résolution accepte `failure_type` et `status_byte`, ou une forme affichée comme `U140A 00 [039]` ; le statut transitoire n’entre jamais dans l’identité. Un statut dans une définition importée est refusé.

`coverage.summary` sépare les génériques historiques non revus des variantes de production, les concepts des lignes et les alias de leurs preuves. Un dénominateur absent donne un ratio `null`, pas une prétendue couverture complète. Voir le [runbook](vag-ingestion-runbook.md) pour le contrat des assertions et les limites Tier C/ODX.
