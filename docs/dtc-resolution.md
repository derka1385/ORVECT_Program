# Résolution multi-namespace des données diagnostic

Le catalogue actif sépare désormais l’identité d’un défaut de sa définition. Un identifiant est unique dans un `namespace`, mais il peut posséder plusieurs variantes de définition. Le modèle relationnel conserve notamment la marque, la plateforme, le modèle, la plage d’années, le code moteur et boîte, le module ECU, ses références, le mode de panne, le sous-type, le corpus source et la provenance de l’enregistrement.

`dtcs` reste temporairement le catalogue de compatibilité pour les codes génériques SAE/OBD-II existants. Les nouveaux corpus utilisent :

- `diagnostic_namespaces` pour `sae_obd2`, `vag_legacy`, `vag_obd`, `vag_uds`, puis les futurs namespaces OEM ;
- `diagnostic_datasets` pour le corpus, sa version, son checksum, sa licence et son dénominateur documenté ;
- `diagnostic_identifiers` pour le code canonique indépendant de `Pxxxx` ;
- `diagnostic_definition_variants` pour les définitions et leurs critères d’applicabilité ;
- `diagnostic_code_aliases` pour les équivalences documentées, notamment vers OBD-II ;
- les journaux de revue pour chaque transition de promotion.

## Résolution progressive

Le resolver écarte d’abord toute variante incompatible avec les métadonnées connues, puis privilégie la variante compatible la plus spécifique : véhicule et plateforme, powertrain, module ECU, références ECU, namespace et identifiant. Une définition n’est résolue que si une seule variante la plus spécifique est pleinement applicable.

Si des champs nécessaires manquent, la réponse est `insufficient_vehicle_configuration`, avec tous les candidats plausibles et `missing_information`. Si plusieurs variantes restent également applicables, la réponse est `ambiguous`. Si aucune définition de production ne convient, la réponse contient exactement `Definition unavailable for this vehicle configuration.`. Le LLM ne reçoit jamais le droit de choisir un candidat.

```bash
curl -X POST http://localhost:8000/api/diagnostic-data/resolve \
  -H 'Authorization: Bearer TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"namespace":"vag_uds","code":"IDENTIFIER_FROM_LICENSED_SOURCE","vehicle_id":"VEHICLE_ID","ecu_module":"engine","ecu_identifiers":["ECU_PART_NUMBER"]}'
```

## Ingestion et promotion

`POST /api/diagnostic-data/imports` accepte le format JSON structuré `1.0`, réservé aux administrateurs. Le manifeste exige une source déjà enregistrée, une licence utilisable explicitement confirmée, un checksum canonique, le nombre documenté disponible dans le corpus, une version et une provenance par définition ou alias. L’import est transactionnel et chaque donnée débute en quarantaine.

La seule séquence autorisée est :

```text
quarantined -> source_matched -> verified -> production
```

Chaque transition est séquentielle, administrateur uniquement et auditée. Depuis la Phase 1.6, `verified` et `production` exigent une source marquée `reviewed`, une évaluation des droits du contenu approuvée et des preuves par champ selon Tier A/B. Une définition ou un alias portant `origin=generated` est définitivement inéligible à la promotion. Le resolver revalide ces preuves à la lecture et bloque les conflits ouverts. Le détail des contrats, sous-types UDS, alias dédupliqués et révocations est dans le [runbook 1.6](vag-ingestion-runbook.md).

Les adaptateurs JSON structurés générique, SAE et OEM partagent le même contrat validé. Les adaptateurs `odx` et `pdx` sont enregistrés derrière cette interface, mais refusent actuellement tout import. Un parseur devra être ajouté pour le profil exact du corpus légalement obtenu ; l’absence de parseur ne déclenche aucun repli approximatif.

## Couverture

`GET /api/diagnostic-data/coverage` groupe par `namespace`, `manufacturer`, `brand`, `ecu_module` ou `code_type`. Le ratio est `définitions documentées couvertes par le resolver / définitions documentées disponibles dans les corpus importés`. Pour le groupe namespace, le dénominateur vient de `documented_available_count` du manifeste, pas du nombre théorique de valeurs hexadécimales. Le rapport distingue les variantes OEM vérifiées de l’ancien catalogue générique actif mais encore non revu indépendamment. Le bloc VAG compte séparément les identifiants constructeur de production avec et sans équivalence OBD-II documentée.

## Quarantaine historique

Les 56 220 lignes écartées de l’ancien catalogue sont conservées dans `quarantine/dtc_catalog_legacy_quarantine.json.gz`. Cette archive est exclue des images Docker, n’est référencée par aucun module runtime et ne peut être servie par le resolver. `scripts/archive_quarantined_dtc_catalog.py` documente le processus reproductible d’archivage.

`python scripts/review_quarantined_dtc.py CODE` localise une ancienne ligne et produit son checksum de revue, sans recopier sa définition dans un manifeste. Lorsqu’une source indépendante et légalement utilisable confirme le code, le nouvel import peut conserver ce checksum dans `provenance.legacy_quarantine_entry_sha256`, puis suivre toutes les transitions normales. L’ancienne définition générée reste inéligible ; seule la nouvelle transcription sourcée peut être promue.

## TODO technique explicite

- importer un corpus VAG réel seulement après acquisition et revue de ses droits d’usage ;
- implémenter les profils ODX/PDX correspondant à ce corpus, avec limites ZIP/XML et tests de conformité ;
- migrer le catalogue générique SAE historique vers le modèle versionné après vérification contre une source SAE légalement exploitable ;
- automatiser la file de revue des rapprochements de quarantaine, sans jamais reprendre le texte historique comme source ;
- acquérir des observations terrain attestées pour activer le Tier C ; la révocation/restauration de dataset et la révocation des droits source sont implémentées en Phase 1.6.
