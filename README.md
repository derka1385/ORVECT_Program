# Orvect

**Orvect is an evidence-backed automotive diagnostic intelligence platform that helps workshops move from fault codes to prioritized diagnostic actions.**

Powered by **Nebius Token Factory** for diagnostic reasoning and **Tavily** for real-time technical evidence.

---

## Problem

Modern diagnostic tools expose codes but technicians still spend significant time researching root causes and testing possibilities.

A scanner says `P0301 — Cylinder 1 Misfire Detected`. It does not say what is most likely causing it *on this vehicle*, what to test first, what not to replace blindly, or how confident anyone should be. That research gap is billable hours, and it is where parts get replaced on a guess.

## Solution

Orvect combines:

- **structured vehicle data** — make, model, year, engine code, mileage, ECU, VIN
- **internal diagnostic knowledge** — a versioned DTC catalogue with per-record provenance
- **Nebius-powered reasoning** — hypothesis generation, evidence synthesis, ranking, test-plan construction
- **Tavily-powered technical research** — OEM bulletins, recall databases, technical documentation

into a prioritized technician workflow: ranked hypotheses, a cheapest-and-fastest-first test sequence, linked evidence, and an explicit confidence heuristic.

## Architecture

```
            Vehicle + DTC(s) + symptoms + measurements
                              |
                              v
                 Orvect diagnostic orchestrator
                              |
              +---------------+----------------+
              |                                |
              v                                v
    Diagnostic Data Resolver          internal knowledge base
    (authoritative DTC identity)      (compatibility-scoped)
              |                                |
              +---------------+----------------+
                              |
                              v
                    Diagnostic Engine (gate)
                  deterministic evidence check
                              |
                              v
                      research decision
              "would external evidence change this?"
                              |
                   no <-------+-------> yes
                   |                     |
                   |                     v
                   |                  Tavily
                   |            1-3 focused queries
                   |                     |
                   |                     v
                   |          external evidence + ranking
                   |          OEM > authority > docs >
                   |          repair resource > forum
                   |                     |
                   +---------+-----------+
                             |
                             v
                   Nebius Token Factory
              one structured reasoning call over
              internal + external evidence
                             |
                             v
                 provenance validation layer
            (citations rebuilt server-side; invented
             sources dropped; boundaries enforced)
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
        hypothesis      diagnostic     confidence
         ranking         test plan      heuristic
              |              |              |
              +--------------+--------------+
                             |
                             v
          Safety Engine (deterministic, never the LLM)
                             |
                             v
                    Technician report
                             |
                             v
                confirmed outcome feedback
              (optional, consented) -> Orvect dataset
```

## Why Nebius

Nebius Token Factory is the reasoning layer. Every diagnostic runs one structured Nebius call that:

- interprets the confirmed fault codes **as one case**, not as independent code lookups
- generates and ranks root-cause hypotheses with supporting and contradicting evidence
- synthesizes internal knowledge and external technical evidence, weighting by source quality
- builds the technician test sequence, ordered cheapest / fastest / least invasive / most informative first

It is called server-side only (`backend/app/modules/diagnostic_ai/nebius.py`), over the OpenAI-compatible
`/chat/completions` endpoint with JSON-schema structured output, falling back to JSON mode and then to
`NEBIUS_FALLBACK_MODEL`. Model choice is entirely environment-driven.

## Why Tavily

Tavily supplies the external automotive evidence the internal knowledge base does not have: manufacturer
bulletins, recall databases, engine-family failure patterns, technician discussions.

Queries are generated from the diagnostic context and are always vehicle-specific — never the bare code:

```
2018 Volkswagen Golf VII 1.4 TSI 92 kW P0301 common causes diagnosis
Volkswagen CZCA P0301 rough idle EPC light technical service bulletin
2018 Volkswagen Golf VII 1.4 TSI 92 kW P0301 recall technical service bulletin
```

Results are classified onto an evidence hierarchy — OEM, safety authority, technical documentation,
repair resource, specialist community, general web — and a forum thread is never weighted like a
manufacturer bulletin. Every externally derived claim keeps its title, domain and clickable URL.

## Cost-efficient architecture

**Orvect does not blindly query the web.** A deterministic research-decision layer runs first and searches
only when external evidence would materially change the diagnosis:

| Search | Because |
|---|---|
| yes | manufacturer-specific code, missing internal definition, multiple codes needing a shared cause, thin internal evidence, engine-specific failure pattern |
| no | internal knowledge already covers the case, or research is disabled |

Searches are capped (`TAVILY_MAX_QUERIES`, default 3), run in parallel, deduplicated by URL, and cached by
`make + model + year + engine + DTC set` for `TAVILY_CACHE_TTL_HOURS`. Repeated research on the same vehicle
configuration costs nothing. Completed analyses are additionally cached per context hash, so re-opening a
case spends no tokens at all.

## Trust model

The LLM is the *explanation layer*, not the authority. Enforced in code, not in the prompt:

- **DTC definitions** are rebuilt server-side from the Diagnostic Data Resolver. The model cannot alter,
  omit or invent one.
- **Citations** are emitted by the model as a bare `source_id`; the server rebuilds every other field. A
  `source_id` that was never in the context is dropped and the claim falls back to `unverified`.
- **No fabricated URLs** — a Tavily result without a real URL is discarded before the model ever sees it.
- **Safety decisions** come from a deterministic `SafetyEngine`. The model never decides whether a vehicle
  can be driven or how dangerous a fault is.
- **No blind part replacement** — affirmative "replace X" recommendations are blocked; "do *not* replace X
  before the simple checks" is a first-class output.
- **Confidence** is a server-side heuristic over evidence quality, labelled *diagnostic confidence*, never
  a probability that a repair will work.
- **Zero hypotheses is a valid answer.** When evidence is insufficient the Diagnostic Engine says so and
  the model is not allowed to fill the gap.

## Future

Confirmed workshop outcomes feed a proprietary Orvect diagnostic dataset. After a repair, a technician can
optionally record the confirmed root cause and what actually fixed the vehicle, alongside the original
context and Orvect's recommendations (`diagnostic_outcomes`). Sharing beyond the garage requires an explicit
consent checkbox. Over time this says which hypotheses proved correct for specific vehicles, engines,
mileages and symptom combinations — data no general-purpose model has. No ML is trained on it today; the
data model is built to make that possible.

## Quickstart

```bash
cp .env.example .env          # then fill NEBIUS_API_KEY and TAVILY_API_KEY
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[test]"
DATABASE_URL=sqlite:///./orvect.db .venv/bin/python -c "from app.seed import seed; seed()"
DATABASE_URL=sqlite:///./orvect.db .venv/bin/python -m uvicorn app.main:app --port 8000
# in another shell
cd frontend && npm install && npm run dev      # http://localhost:3000/diagnostics/new
```

Runs anonymously in development — no account needed to reach the diagnostic flow. `LLM_PROVIDER=mock`
gives a fully deterministic run with no API keys and no network.

**Demo:** open `/diagnostics/new`, pick **Golf VII 1.4 TSI · P0301 + EPC** from the demo cases, confirm the
codes, and launch. The demo only prefills the intake form — the diagnosis itself always runs the real
pipeline. `Golf VII · trois codes corrélés` shows multi-DTC shared-root-cause analysis; `BMW 320d N47`
shows a different make, engine and fault.

## Environment variables

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `nebius` (primary), `gemini`, or `mock` |
| `NEBIUS_API_KEY` | Nebius Token Factory key — **server-side only** |
| `NEBIUS_MODEL` / `NEBIUS_FALLBACK_MODEL` | benchmarked on the live catalog: `openai/gpt-oss-120b` (~26 s), fallback `deepseek-ai/DeepSeek-V4.1-Flash` |
| `TAVILY_API_KEY` | Tavily key — **server-side only** |
| `TAVILY_MAX_QUERIES` | hard cap on searches per diagnostic (default 3) |
| `TAVILY_CACHE_TTL_HOURS` | research cache lifetime (default 168) |
| `RESEARCH_ENABLED` | `false` disables all external research |

No key is ever sent to the browser: the frontend talks only to `/backend-api`, and every provider call is
made from the FastAPI process. Provider errors are mapped to safe messages before they reach a user.

---

# Documentation technique (FR)

## ORVECT — prototype de diagnostic automobile assisté

ORVECT aide un mécanicien à transformer un DTC en parcours de contrôle guidé, sourcé et traçable. Ce dépôt est une fondation fonctionnelle et un **prototype technique à ne pas utiliser sur un véhicule réel**. Un DTC n’est jamais présenté comme la preuve d’une pièce défectueuse.

## Démonstration publique

La page [derka1385.github.io/ORVECT_Program](https://derka1385.github.io/ORVECT_Program/) présente le parcours officiel avec des données exclusivement synthétiques. GitHub Pages charge l’interface statique, puis appelle l’API FastAPI authentifiée sur `https://orvect-api.onrender.com/api`. PostgreSQL est hébergé sur Neon et la clé Gemini reste exclusivement dans les variables secrètes du backend Render.

Trois cas synthétiques sont chargeables sur téléphone : [ratés d’allumage](https://derka1385.github.io/ORVECT_Program/?demo=golf-misfire), [observation du connecteur](https://derka1385.github.io/ORVECT_Program/?demo=golf-connector), [définition manquante](https://derka1385.github.io/ORVECT_Program/?demo=golf-unknown). Ils restent préremplis localement, mais une analyse exige une connexion et déclenche un vrai appel Gemini via le backend officiel. Le plan Render gratuit peut imposer un réveil d’environ une minute après une période d’inactivité.

Le [formulaire public et anonyme de retour atelier](https://derka1385.github.io/ORVECT_Program/collecte/) permet de documenter un cas réel sans demander l’identité de l’atelier ou du technicien. Il génère un TXT lisible et un JSON structuré, partageables sur iPhone par Mail ou AirDrop et téléchargeables ailleurs. Les JSON reçus se compilent ensuite en JSONL et CSV avec `python3 scripts/compile_workshop_cases.py` ; voir `collecte/README.md`.

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
- interface ORVECT responsive en quatre étapes — entrée, identification, problème/preuves et diagnostic assisté — plus rapport Next.js ;
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

`/` ouvre l’entrée atelier : création d’un dossier, reprise d’un diagnostic récent, sélection d’un véhicule existant ou identification par plaque/VIN. `DEMO123` reste disponible pour les tests hors ligne. Pour une plaque réelle, utilisez un fournisseur professionnel autorisé qui retourne au minimum un VIN :

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
