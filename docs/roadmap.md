# Roadmap

## MVP 0
Architecture, modèles, données fictives, sessions, moteur de règles, mock IA, interface métier et tests.

## MVP 1
Authentification locale minimale réalisée. Restent : MFA/SSO et récupération de compte, sélection multi-garage explicite, sessions/rate limiting distribués, imports enrichis, recherche documentaire licenciée, rapports et feedback mécanicien.

## Dette technique explicite du socle

- remplacer la migration initiale mutable par un historique Alembic entièrement figé puis tester la montée depuis chaque version supportée ;
- retirer les colonnes historiques `users.garage_id`, `users.role` et `vehicle_profiles.vin` après une période de migration ;
- ajouter un corpus SAE/constructeur sous licence et revu avant d’activer davantage de définitions ou procédures ;
- ajouter une file transactionnelle pour la purge physique des images et une politique de sauvegarde garantissant l’effacement ;
- faire auditer les règles du Safety Engine par un expert automobile avant toute utilisation réelle.

## MVP 2
Ingestion autorisée, recherche hybride, embeddings/RAG, versions, validation humaine et analytics.

## MVP 3
Connecteur local en lecture seule, imports de valises compatibles, OBD live, multi-véhicules et intégrations fournisseurs/pièces.

## Version professionnelle
Sécurité renforcée, audit, licences, haute disponibilité, cloud, conformité, supervision, support atelier et validation terrain.
