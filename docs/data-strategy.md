# Stratégie de données

La valeur et la sécurité du produit reposent d’abord sur une base de connaissances fiable, versionnée et révisée, pas sur le modèle de langage.

1. **Phase 1 — démonstration** : corpus fictif, scénarios contrôlés, règles manuelles, validation logicielle. Chaque item porte `demo_only: true`.
2. **Phase 2 — sources publiques ou autorisées** : codes OBD génériques, licences compatibles, manuels appartenant à l’entreprise et contenu produit par des garages partenaires. Aucun scraping protégé ni contournement d’accès.
3. **Phase 3 — licences professionnelles** : fournisseurs techniques, pièces, temps de main-d’œuvre, schémas, bulletins, procédures et VIN, avec provenance et droits documentés.
4. **Phase 4 — retours terrain** : DTC, symptômes, mesures, réparation, confirmation, variante, temps, pièces et retour mécanicien. Ces données restent candidates jusqu’à revue humaine.

Les imports sont validés, hachés, versionnés, dédupliqués puis appliqués dans une transaction. Une source peut devenir `outdated` ou `rejected` sans supprimer l’historique. La promotion vers les règles actives exige une revue humaine et une licence compatible.

## Catalogue générique actif

Le catalogue historique contenait 65 536 lignes. La Phase 1 avait isolé 56 220 lignes et conservé 9 316 lignes étiquetées génériques. L’audit 1.6 a démontré que 383 d’entre elles provenaient exactement de lignes non génériques `other_codes` du snapshot Wal33D, et que 13 autres étaient mal classées dans des plages constructeur. Les 396 lignes ont été archivées séparément. Restent **8 920** correspondances exactes de la compilation communautaire, toujours `unreviewed` / `verified: false`, sans validation contre une édition licenciée SAE J2012DA. La licence MIT déclarée ne démontre pas les droits sous-jacents ; l’évaluation structurée les marque incertains. Voir [l’inventaire et les preuves](vag-data-source-inventory.md).

Les codes constructeur ne sont jamais complétés par famille. Sans source exacte compatible avec la configuration du véhicule, le résolveur retourne littéralement `Definition unavailable for this vehicle configuration.`. P1351 est couvert par ce test de non-régression.

## Catalogue OEM versionné

La Phase 1.5 ajoute un modèle multi-namespace qui n’impose plus `Pxxxx`. Il permet plusieurs définitions d’un même identifiant selon véhicule, plateforme, powertrain, ECU et année, ainsi que des alias OBD-II uniquement lorsqu’ils ont leur propre provenance. L’import ne publie jamais directement une définition : `quarantined → source_matched → verified → production`, avec revue administrateur et source légalement utilisable.

Le premier namespace OEM déclaré est `vag_uds`, couvrant structurellement Volkswagen, Audi, Škoda, SEAT/CUPRA et Volkswagen Commercial Vehicles via le champ d’applicabilité `brand`. Aucun intitulé VAG réel n’est livré dans le dépôt : ajouter des définitions sans corpus licencié contredirait la règle de zéro fabrication. ODX et PDX sont des adaptateurs enregistrés en refus explicite jusqu’à l’implémentation d’un profil correspondant à un corpus légal.

L’ancien contenu écarté n’est pas perdu : 56 220 lignes restent dans l’archive compressée `quarantine/dtc_catalog_legacy_quarantine.json.gz`. L’archive est volontairement absente des images et du code runtime ; elle sert uniquement à une future mise en correspondance contrôlée.
