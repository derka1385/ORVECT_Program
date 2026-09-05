# ORVECT — prototype de diagnostic automobile assisté

ORVECT aide un mécanicien à transformer un DTC en parcours de contrôle guidé, sourcé et traçable. Ce dépôt est une fondation fonctionnelle et un **prototype technique à ne pas utiliser sur un véhicule réel**. Un DTC n’est jamais présenté comme la preuve d’une pièce défectueuse.

## Démonstration publique

La page [derka1385.github.io/ORVECT_Program](https://derka1385.github.io/ORVECT_Program/) présente un parcours interactif avec des données exclusivement synthétiques. GitHub Pages étant un hébergement statique, cette démonstration n’exécute ni FastAPI, ni PostgreSQL, ni l’authentification serveur et ne conserve aucune donnée. Le runtime complet et sécurisé se lance avec Docker selon la procédure ci-dessous.

La vérification DTC de la page statique charge localement les 8 920 définitions génériques du catalogue communautaire filtré. Elles sont affichées avec leur provenance et comme non revues contre la version SAE sous licence. Les codes constructeur non documentés restent volontairement sans définition. Après une mise à jour du JSON source, régénérer l’index utilisable hors ligne avec `node scripts/build_static_dtc_lookup.mjs`.

## Ce qui fonctionne

- utilisateurs administrateur/technicien, garage et véhicule de démonstration ;
- quatre DTC de démonstration, connaissances atomiques et règles sourcées ;
- catalogue actif limité à 8 920 lignes communautaires génériques non revues ; 56 220 lignes historiques et 396 lignes supplémentaires mal classées ont été mises en quarantaine ; aucune couverture exhaustive ni autorité SAE n’est revendiquée ;
- import OBD canonique JSON/CSV sans connexion physique ;
- scénario P0301 interactif avec branches « le défaut suit la bobine » / « reste sur le cylindre 1 » ;
- parcours générique sûr pour tout code DTC syntaxiquement valide, y compris les codes constructeur non définis comme P1351 ;
- hypothèses éventuellement vides, états d’insuffisance explicites, preuves/contradictions, étape courante, événements immuables et rapport ;
- mock LLM strictement validé et désactivable sans casser le moteur ;
- interface ORVECT responsive et pleine largeur en quatre étapes — identification VIN ou plaque, vérification technique éditable, DTC multiples/symptômes et résultats — plus rapport Next.js ;
- authentification par session opaque, rôles `admin`/`technician` et isolation du garage dérivée côté serveur ;
- résolution VIN avec mock hors ligne, adaptateur NHTSA vPIC optionnel, cache HMAC, confirmation technicien et rapprochement ECU/DTC.
- diagnostic multimodal avec codes multiples, mesures, photos privées, sortie JSON stricte et provider Gemini interchangeable ;
- mode `mock` déterministe utilisable sans clé pour tester intégralement P1351 et le parcours de réévaluation.

## Stack et structure

FastAPI, Pydantic, SQLAlchemy, Alembic, pytest ; Next.js 16, React 19, TypeScript strict et Tailwind ; PostgreSQL avec Docker Compose, SQLite en local. Le backend est un monolithe modulaire (`vehicles`, `obd`, `knowledge`, `diagnostics`, `vehicle_resolution`, `ai`, `garages`, `reports`, `imports`). Les décisions sont détaillées dans [docs/architecture.md](docs/architecture.md).

## Démarrage recommandé avec Docker

```bash
# Seulement si .env n’existe pas déjà : cp .env.example .env
LLM_PROVIDER=mock docker compose up -d --build --wait --wait-timeout 240
```

Les migrations et fixtures sont appliquées au démarrage du backend. Le frontend attend que le backend soit sain ; les contrôles de santé vérifient PostgreSQL et le proxy. Interface : http://localhost:3000 ; API : http://localhost:8000/api/health. Les ports ne sont exposés que sur la boucle locale. Arrêt sans perte des volumes : `docker compose down`. Ne pas utiliser `down -v` pour un simple redémarrage : cela détruirait les données.

La base SQLite historique de 1 234 DTC a été retirée du runtime et intégralement archivée. Le PostgreSQL existant a été sauvegardé puis migré sans effacer ses véhicules ni ses diagnostics. Voir [le rapport et les procédures de vérification/restauration](docs/local-runtime-validation.md). Vérification reproductible, sans fournisseur IA externe : `backend/.venv/bin/python scripts/smoke_local_runtime.py` après le démarrage en mode `mock` ci-dessus. Un simple `docker compose up` sans cette variable reprend le fournisseur configuré dans votre `.env`.

En développement uniquement, la fixture crée `admin@example.com` / `demo-change-me` et `technician@example.com` / `demo-tech-change-me`. Ces mots de passe doivent être vides en production ; le backend refuse sinon de démarrer.

## Démarrage local

Prérequis : Python 3.11+ et Node 22+.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-test.lock
pip install --no-deps -e .
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

Dans un second terminal :

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000/api npm run dev
```

## Tests et contrôles

```bash
cd backend
DATABASE_URL=sqlite:///./test.db pytest

# ou, sans Python local :
docker build -f backend/Dockerfile.test -t diagpilot-backend-test .
docker run --rm diagpilot-backend-test

cd ../frontend
npm run typecheck
npm run build
npm audit --audit-level=high

cd ../backend
pip-audit -r requirements.lock --no-deps --disable-pip
```

## URLs locales

- application : http://localhost:3000
- santé API : http://localhost:8000/api/health
- Swagger : http://localhost:8000/docs
- OpenAPI : http://localhost:8000/openapi.json

## Démonstration IA P1351

Le mode par défaut est `LLM_PROVIDER=mock` : aucune clé ni donnée externe n’est nécessaire.

1. Ouvrir `http://localhost:3000/diagnostics/new`.
2. Garder le véhicule de démonstration, ou saisir la plaque fictive `DEMO123`.
3. Conserver `P1351` : sans documentation Peugeot compatible, le résultat doit rester `manufacturer_specific` avec « Definition unavailable for this vehicle configuration. », zéro hypothèse forcée et escalade humaine. Ajouter éventuellement `P0301` pour tester une définition générique sourcée.
4. Ajouter une mesure ou une photo, vérifier la synthèse, puis lancer l’analyse.
5. Dans la console IA, renseigner le résultat du contrôle et demander la réévaluation.

Pour activer Gemini, renseigner `GEMINI_API_KEY` dans `.env` et passer `LLM_PROVIDER=gemini`, puis reconstruire le backend. La clé reste exclusivement côté serveur. Voir [docs/vehicle-diagnostic-ai.md](docs/vehicle-diagnostic-ai.md).

## Identification du véhicule

`/diagnostics/new` ouvre l’identification : le technicien choisit strictement un VIN ou une plaque, puis relit et corrige la configuration détectée avant de saisir les DTC. Chaque DTC peut être ajouté, édité, supprimé, confirmé ou signalé comme discordant ; l’analyse reste bloquée tant que tous les codes ne sont pas confirmés. `DEMO123` reste disponible pour les tests hors ligne. Pour une plaque réelle, utilisez un fournisseur professionnel autorisé qui retourne au minimum un VIN :

```env
REGISTRATION_PROVIDER=http
REGISTRATION_API_URL=https://endpoint-fourni-par-votre-prestataire
REGISTRATION_API_KEY=votre_cle_serveur
```

Le connecteur envoie côté serveur `{"registration":"AB123CD","countryCode":"FR"}` avec un jeton Bearer. Il reconnaît les champs usuels `vin`, `make`/`brand`, `model`, `engineCode`, `transmissionType`, etc. Si le contrat du prestataire diffère, adaptez uniquement `vehicle_data/providers.py`; aucune plaque ni clé ne transite dans le frontend.

## Démonstration historique P0301

1. Ouvrir « Nouveau diagnostic » et garder le véhicule Demo Motors DM-1.
2. Saisir P0301, vérifier la plainte et lancer l’analyse.
3. Dans la console, confirmer l’un des résultats de permutation.
4. Observer le nouveau classement et l’étape suivante.
5. Clôturer puis consulter le rapport sourcé.

Pour vérifier spécifiquement le parcours constructeur prudent :

```bash
python3 scripts/smoke_p1351.py
```

## Démonstration VIN

Ouvrir `/vehicle-resolution` et conserver `ZZZTESTA0DEMA0001`. Le mock retourne une DM-1 fictive, puis demande une confirmation avant de créer le véhicule. Les scénarios B à E couvrent moteur manquant, candidats multiples, conflit ECU et fournisseur indisponible. Voir [docs/vin-resolution.md](docs/vin-resolution.md).

Import alternatif : envoyer `data/fixtures/demo_obd_report.json` à `POST /api/imports/obd-report`, ou utiliser Swagger. Aucun effacement de code ni commande ECU n’a lieu.

Le catalogue sous `data/fixtures/dtc_catalog.json` est chargé de façon idempotente par `python -m app.seed`. Ses intitulés anglais sont conservés tels quels. Ils proviennent de Wal33D DTC Database au commit documenté dans le fichier ; ils n’ont pas été vérifiés indépendamment contre l’annexe SAE J2012DA sous licence.

Le catalogue OEM versionné accepte des identifiants indépendants de `Pxxxx`, plusieurs variantes par ECU/véhicule et des alias documentés entre namespaces. Les imports structurés sont mis en quarantaine puis doivent parcourir `source_matched → verified → production`. Les 56 220 anciennes lignes approximatives sont conservées hors runtime dans une archive de quarantaine. Voir [docs/dtc-resolution.md](docs/dtc-resolution.md).

## Limites actuelles

L’authentification locale est réelle mais minimale : provisionnement/récupération de compte, MFA/SSO, sélection explicite entre plusieurs garages et stockage distribué des sessions restent à réaliser avant production. Le fournisseur de plaques officiel, le rate limiting distribué, l’antivirus/CDR, l’OCR dédié, la documentation constructeur licenciée, les parseurs ODX/PDX profilés et la connexion OBD sont hors MVP. Aucun corpus VAG réel n’est inclus tant que ses droits d’usage ne sont pas établis ; les identifiants VAG des tests sont explicitement synthétiques. Voir [docs/security.md](docs/security.md) et [docs/roadmap.md](docs/roadmap.md).
