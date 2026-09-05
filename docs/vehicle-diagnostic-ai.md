# Diagnostic automobile multimodal

## Fonctionnement

Le nouveau parcours `/diagnostics/new` crée un dossier lié à un véhicule confirmé, ajoute un ou plusieurs DTC, des mesures facultatives et jusqu’à huit images, puis déclenche une analyse. Le backend assemble un contexte canonique sans VIN ni plaque, l’envoie au provider sélectionné et valide la réponse contre `DiagnosticAnalysis` avec `extra="forbid"` et des confiances bornées entre 0 et 1.

Le résultat LLM contient synthèse, codes interprétés, corrélations, zéro ou plusieurs hypothèses, éléments visuels, informations manquantes, contrôles suivants, conclusion et avertissements. La sécurité est ajoutée séparément par le moteur déterministe du serveur. Les étapes et hypothèses sont persistées avec leurs références complètes ; seul un résultat `positive` ou `negative` réellement informatif peut modifier l’état diagnostique.

```text
plaque/VIN -> configuration confirmée -> DTC + mesures + images
                                          |
                              contexte filtré et versionné
                                          |
                      Diagnostic Engine + contexte sourcé
                                          |
                      mock ou Gemini (explication seulement)
                                          |
                 validation stricte + Safety Engine déterministe
```

## Providers

- `mock` est le défaut : déterministe, hors ligne, prudent et adapté aux tests.
- `gemini` utilise le SDK Python `google-genai`, les images en données binaires et un schéma Pydantic. Le modèle rapide traite les dossiers simples ; le modèle de raisonnement traite les dossiers multi-codes et les suivis.
- une abstraction `AutomotiveAIProvider` évite de lier le domaine à Gemini.
- une seule tentative de réparation structurée est autorisée après une réponse invalide ; un second échec est enregistré et renvoie une erreur sûre.

Configuration serveur :

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=votre_cle_serveur
GEMINI_MODEL_FAST=gemini-3.1-flash-lite
GEMINI_MODEL_REASONING=gemini-3.5-flash
GEMINI_TIMEOUT_SECONDS=45
GEMINI_MAX_OUTPUT_TOKENS=8192
```

La clé ne doit jamais être préfixée par `NEXT_PUBLIC_`, copiée dans le frontend, journalisée ou persistée en base. Les quotas réels dépendent du projet Google ; le limiteur local n’est qu’une protection supplémentaire.

## Images et confidentialité

Les formats acceptés sont JPEG, PNG et WebP. Pillow valide le contenu réel, corrige l’orientation EXIF, redimensionne à 2 400 px, convertit en JPEG et supprime les métadonnées. Les fichiers portent un UUID, restent dans un volume backend privé et sont servis par une route qui vérifie le garage. Les chemins physiques ne sortent jamais de l’API. Une purge paresseuse supprime les images au-delà de la durée configurée (90 jours par défaut).

Le texte saisi ou visible dans une image est marqué comme donnée non fiable. Le prompt interdit d’exécuter des instructions trouvées dans ces champs. Le contexte Gemini exclut les identifiants directs du véhicule.

## Plaque et VIN

`VehicleDataProvider` sépare la recherche par plaque de l’identification VIN. Le provider de démonstration reconnaît uniquement `DEMO123`; toute plaque réelle est bloquée tant que le connecteur professionnel n’est pas configuré. Une intégration réelle doit utiliser un fournisseur autorisé dans le pays concerné et respecter sa base légale.

Le provider `http` permet maintenant de raccorder un service professionnel sans exposer sa clé. L’interface n’accepte que la plaque ; le fournisseur doit retourner le VIN et peut retourner directement les données moteur/transmission. Il ne faut pas remplacer ce connecteur par du scraping de sites destinés aux particuliers.

À la confirmation, la plaque normalisée est chiffrée et son empreinte HMAC permet la recherche/déduplication ; l’interface ne reçoit que les derniers caractères. Le VIN suit déjà le même principe dans les demandes de résolution.

## Résilience et audit

- délai maximum configurable ; trois essais seulement pour HTTP 429/5xx ;
- verrou applicatif pendant une analyse et limite par garage ;
- idempotence par hash du contexte, version du prompt et type d’opération ;
- journal `ai_calls` : provider, modèle, statut, hashes, latence, tokens, validation et erreur sûre ;
- événements métier et anciennes hypothèses conservés, étapes antérieures marquées comme remplacées ;
- aucune sortie brute ou pensée interne du modèle n’est stockée.

## Limites avant production

L’authentification locale par session et rôles est en place. Il reste à ajouter MFA/SSO, provisionnement et récupération de compte, support multi-garage explicite, puis à déporter sessions/rate limiting dans un stockage partagé. Il faut aussi ajouter analyse antivirus/Content Disarm si nécessaire, planifier la purge hors requête, brancher un stockage objet chiffré, définir la résidence des données, obtenir les licences documentaires constructeur et faire valider les usages IA/plaques par le DPO et le conseil juridique.

## Tests

```bash
cd backend
pytest

cd ../frontend
npm run typecheck
npm run build
```

Les tests couvrent P1351 et les multi-codes, le schéma strict, la réparation Gemini, la clé absente, l’isolation garage, la validation réelle des images, l’injection de prompt dans les données non fiables, le chiffrement de plaque, l’idempotence et la réévaluation.
