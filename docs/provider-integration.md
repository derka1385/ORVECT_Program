# Intégration des fournisseurs VIN

Les fournisseurs implémentent `VinProvider.decode(vin, country_code, model_year_hint)` et renvoient uniquement `VinProviderResult`. Ajouter l’adaptateur dans `providers/`, son mapping dans `VinNormalizer`, puis l’enregistrer dans `registry.py`. L’application ne dépend ainsi jamais des noms de champs externes.

Pour NHTSA en développement : `VIN_PROVIDER=nhtsa_vpic` et `NHTSA_VPIC_ENABLED=true`. Le client asynchrone utilise `DecodeVinValuesExtended`, un timeout configurable et deux retries réservés aux pannes transitoires. vPIC est à dominante nord-américaine : confirmer les résultats européens.

Avant TecAlliance ou un OEM, vérifier contrat, territoire, sous-traitance, durée de cache, suppression, attribution, quotas, export et conservation. Ajouter les secrets dans l’environnement, des tests HTTP simulés, le mapping canonique et le mode dégradé.
