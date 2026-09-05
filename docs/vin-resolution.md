# Résolution VIN

Le flux est : validation → cache HMAC → fournisseur → normalisation canonique → candidats → confirmation technicien → ECU → précision → compatibilité DTC. Le VIN ne produit jamais directement un diagnostic.

Le fournisseur par défaut est `mock`, sans réseau. Les scénarios A à E sont dans `data/fixtures/mock_vin_scenarios.json`. Le cache est isolé par garage, indexé par empreinte HMAC et expire selon `VIN_CACHE_TTL_DAYS`. `force_refresh=true` permet de l’ignorer.

```bash
curl -X POST http://localhost:8000/api/vehicle-resolution/vin -H 'Content-Type: application/json' -d '{"vin":"ZZZTESTA0DEMA0001","country_code":"FR"}'
```

Confirmer ensuite le `candidate_id` via `POST /api/vehicle-resolution/{id}/confirm`. Une indisponibilité retourne `provider_failed` et laisse possible la saisie manuelle.
