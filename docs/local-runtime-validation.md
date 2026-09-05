# Validation du runtime local — 4 septembre 2026

> **Mise à jour du 5 septembre 2026 :** ce document conserve la preuve de la validation réussie au moment indiqué, mais la stack Docker n'est plus pleinement opérationnelle. Le backend répond encore sur `/api/health`, tandis que le proxy frontend `/backend-api/health` retourne HTTP 500 et les requêtes utilisant PostgreSQL se bloquent. Le CLI et l'interface Docker Desktop ne répondent plus ; les logs hôte montrent `no space left on device` puis un timeout de cinq minutes du backend Docker. Aucun volume, conteneur, dump ni fichier historique n'a été supprimé pour tenter une réparation à l'aveugle. Le fallback local mock/SQLite décrit dans `docs/demo-runbook.md` passe le smoke test complet, mais ne remplace pas la remise en état de Docker/PostgreSQL.

## Résultat et périmètre

Le monolithe modulaire fonctionne dans Docker avec PostgreSQL, FastAPI et Next.js.
Les services restent démarrés ; les ports 3000 et 8000 sont accessibles uniquement
sur localhost. Cette validation utilise **LLM_PROVIDER=mock**, sans requête Gemini
ni transmission des anciens dossiers à un fournisseur externe. Le fichier `.env`
existant n’a pas été modifié. La disponibilité du fournisseur Gemini n’est donc
pas certifiée par ces tests.

Aucune nouvelle fonctionnalité automobile, aucun import VAG et aucun microservice
n’ont été ajoutés pendant cette intervention.

## Sort exact de SQLite

Ancien emplacement : `backend/diagnostic.db`. Base sans table `alembic_version`,
antérieure au schéma courant. `integrity_check=ok`, aucune violation de clé étrangère.
Les « 1 234 lignes » désignaient les DTC, et non toutes les lignes de la base.

| Données non vides | Lignes |
| --- | ---: |
| DTC | 1 234 |
| Garage de démonstration | 1 |
| Technicien de démonstration, sans mot de passe | 1 |
| Véhicule fictif Demo Motors DM-1 | 1 |
| Sources | 2 |
| Connaissances de démonstration | 4 |
| Règle de démonstration | 1 |
| **Total** | **1 244** |

Les autres tables sont vides : aucun diagnostic, événement diagnostic, appel IA,
VIN ou dossier de résolution véhicule à transférer. Les identifiants des objets
de démonstration correspondent aux fixtures. Les 1 234 codes existent déjà dans
la fixture actuelle : 1 230 libellés identiques et quatre anciens libellés démo.

**Décision : retrait du runtime, pas de migration ni de fusion de SQLite dans
PostgreSQL. Aucune ligne SQLite n’a été supprimée.** Le fichier original a été
déplacé intégralement, sans modification de ses octets, et une seconde sauvegarde
SQLite cohérente a été créée et contrôlée. Aucun processus n’utilisait le fichier
lors du retrait ; aucun journal/WAL annexe n’était présent.

Archives privées, ignorées par Git et les contextes Docker :

- `.local/backups/runtime-20260904/sqlite/diagnostic.original.db`
- `.local/backups/runtime-20260904/sqlite/diagnostic.snapshot.db`
- `.local/backups/runtime-20260904/sqlite/manifest.json`

Les fichiers ont les permissions `0600`, le répertoire d’archive `0700`.
Empreinte SHA-256 de l’original conservé :
`05f5c06a98c09b4d2660fe003350650b8a38b51d3eb4fb2775ec992c6a877c66`.
Le manifeste fournit les compteurs de toutes les tables et les deux empreintes.
L’ancien chemin `backend/diagnostic.db` n’existe plus. Une exécution Python hors
Docker utilisant les paramètres par défaut peut créer une **nouvelle** SQLite ;
elle n’est pas le stockage de la stack validée.

Pour consulter/restaurer l’historique, copier l’original vers un **nouvel**
emplacement de travail et ouvrir cette copie en lecture seule. Ne pas écraser une
base active ni utiliser l’ancien schéma directement avec le backend actuel.

## PostgreSQL : sauvegarde, migration et conservation

Le volume existait déjà, mais aucun conteneur du projet ne tournait. Il contenait
un schéma **0005**, six véhicules, douze diagnostics, un utilisateur et 1 234 DTC.
Il n’a été ni réinitialisé ni remplacé.

Avant migration, sauvegarde complète au format `pg_dump -Fc` :

- `.local/backups/runtime-20260904/postgres/diagnostic.pgdump`
- `.local/backups/runtime-20260904/postgres/manifest.json`
- SHA-256 : `58b0a37cb5f81077b8236b8e95319b39381c5b7e2da52d6d68afd43796eb67d0`

La sauvegarde a été effectivement restaurée dans une base séparée, puis comparée
à la base active : **tous les identifiants historiques des 19 tables métier sont
présents**. Ont notamment été conservés sans modification de leurs colonnes
historiques : six véhicules, douze diagnostics, treize observations, 58 événements
diagnostic, 42 hypothèses, 31 étapes, vingt appels IA et une image. Les huit
candidats de configuration, cinq configurations, 93 événements de résolution et
quarante demandes de résolution VIN sont également conservés. Le fichier de
l’image historique et sa miniature existent toujours dans le volume persistant.

Migration effective : **0005 → 0006 → 0007 → 0008 → 0009 (head)**.
`alembic check` ne détecte plus d’écart avec les modèles. Le parcours depuis une
base PostgreSQL vide jusqu’à 0009, le seed et le contrôle de schéma ont également
été exécutés avec succès dans une base séparée.

Changements attendus du seed courant, et non pertes de données :

- les 1 234 anciens identifiants DTC restent présents ; la fixture actuelle ajoute
  7 686 codes, soit **8 920 lignes** au total, sans promotion OEM/VAG ;
- quatre anciens libellés/sources démo sont remplacés par leur entrée dans la
  fixture courante ; les métadonnées de la source catalogue sont actualisées ;
- l’adresse du technicien démo est alignée sur la configuration actuelle ; un
  administrateur, les mots de passe et les adhésions nécessaires sont initialisés ;
- les anciennes valeurs restent récupérables dans la sauvegarde pré-migration.

Les bases temporaires `runtime_restore_20260904` et `runtime_fresh_20260904` ont
ensuite été supprimées. La base `diagnostic`, ses volumes et les sauvegardes n’ont
pas été supprimés. Les créations de véhicules/diagnostics/images des tests HTTP
sont supprimées par leur identifiant propre ; les sessions d’authentification de
test sont révoquées à la déconnexion et restent dans la table des sessions.

Une restauration future du dump doit d’abord se faire dans une **autre base**
avec `pg_restore --exit-on-error`, puis être contrôlée avant toute bascule.
Le dump ne remplace pas une sauvegarde du volume des images. Les archives locales
ne constituent pas une sauvegarde hors machine.

## Corrections effectuées

1. Migration 0007 : comparaison booléenne portable (`false` au lieu de `=0`,
   invalide pour une colonne booléenne PostgreSQL).
2. Modèles SQLAlchemy : déclaration des index existants de 0004 et de la contrainte
   d’unicité créée par 0007. Le schéma historique et le schéma créé à neuf concordent,
   sans suppression d’index ni nouvelle migration artificielle.
3. Docker : attente de santé backend avant frontend, contrôle backend incluant
   PostgreSQL, contrôle frontend incluant son proxy, redémarrage `unless-stopped`,
   signaux transmis directement à Uvicorn et écoute explicite de Next sur `0.0.0.0`
   dans son conteneur. Les ports publiés restent limités à `127.0.0.1` sur l’hôte.
4. Contextes de build : exclusion des `.env`, fichiers privés et artefacts locaux.
5. Image de tests : imports des tests depuis l’arborescence de travail plutôt que
   depuis le paquet installé, qui exclut volontairement `app.tests`.
6. Résultats historiques IA 1.0 : ils provoquaient dans le navigateur
   `Cannot read properties of undefined (reading 'status')`. L’API ne présente
   désormais comme actuelle qu’une analyse 2.0 validée ; sinon elle indique
   `legacy_requires_review`. L’écran affiche « Analyse historique conservée ».
   Le contenu enregistré est intact ; aucune décision de sécurité ni source n’est
   inventée pour convertir l’ancien résultat. Sa réanalyse nécessite une action
   explicite et produit un nouveau résultat.
7. URL des images : mapping correct de `/api/...` vers `/backend-api/...`, sans
   doubler `/api` dans la réécriture Next.
8. CI : ajout d’un parcours Docker PostgreSQL + frontend, Alembic, tests HTTP et
   redémarrage. Ce job a été ajouté mais pas exécuté sur GitHub pendant cette
   intervention ; ses opérations ont été vérifiées localement.

## Vérifications

- Backend local : **108 tests réussis**, aucun échec.
- Image Docker de tests sans archive de quarantaine : **107 réussis, un test
  explicitement ignoré** car cette archive est exclue des images runtime.
- Nouvelle exécution Docker avec la quarantaine montée en lecture seule :
  **108 tests réussis, aucun test ignoré**, en 61,22 secondes.
- Build frontend de production dans Docker : réussi, Next.js 16.3.4.
- `npm run typecheck` : réussi.
- `npm audit --audit-level=high` : zéro vulnérabilité signalée.
- `pip-audit` des deux lockfiles Python : aucune vulnérabilité connue signalée.
- PostgreSQL existant et PostgreSQL neuf : migration et `alembic check` réussis.
- Tests HTTP via `http://localhost:3000/backend-api` : connexions admin/technicien,
  refus sans authentification et mauvais mot de passe, listing et détail des six
  véhicules et douze diagnostics, création et suppression d’un véhicule fictif,
  diagnostic P1351, analyse 200 avec zéro hypothèse et définition indisponible,
  upload/lecture d’image, conservation du résultat courant et nettoyage en cascade.
- Navigateur réel : connexion et formulaire chargés ; ouverture d’un ancien
  diagnostic sans crash, avec l’avertissement de révision nécessaire.
- Redémarrage backend/frontend testé ; nouveaux contrôles fonctionnels réussis.
- Derniers journaux des conteneurs : aucune réponse HTTP 500 ni traceback.
- Dernière inspection : les trois conteneurs sont `running / healthy`, chacun
  avec `RestartCount=0` après la dernière reconstruction.

Un avertissement de dépréciation Starlette/TestClient demeure ; il ne fait pas
échouer les tests. Les limitations de données automobiles, des anciens résultats
nécessitant une revue, des secrets de développement et de la validation Gemini
ne doivent pas être confondues avec la santé du runtime Docker.

## Commandes de reprise

Depuis la racine du dépôt, sans remplacer le `.env` existant :

```bash
LLM_PROVIDER=mock docker compose up -d --build --wait --wait-timeout 240
docker compose ps
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
backend/.venv/bin/python scripts/smoke_local_runtime.py
```

Arrêt conservant les données : `docker compose down`. Ne pas utiliser `down -v`.

## Fichiers modifiés pendant cette intervention uniquement

Le dépôt était déjà largement modifié avant cette demande ; les autres changements
préexistants ont été conservés. Aucune opération Git destructive ni commit.

```text
.dockerignore
.gitignore
.github/workflows/ci.yml
README.md
docker-compose.yml
backend/.dockerignore
backend/Dockerfile
backend/Dockerfile.test
backend/alembic/versions/0007_foundation_hardening.py
backend/app/api.py
backend/app/database/models.py
backend/app/modules/diagnostic_ai/routes.py
backend/app/tests/test_runtime_operations.py
backend/pyproject.toml
frontend/.dockerignore
frontend/Dockerfile
frontend/src/app/diagnostics/ai/[id]/page.tsx
frontend/src/types/index.ts
scripts/backup_local_postgres.py
scripts/retire_legacy_sqlite.py
scripts/smoke_local_runtime.py
docs/local-runtime-validation.md
```

En dehors des sources : archives locales décrites ci-dessus, retrait récupérable
de `backend/diagnostic.db`, images Docker reconstruites et données PostgreSQL
migrées. Les artefacts ordinaires de tests/build restent ignorés par Git.
