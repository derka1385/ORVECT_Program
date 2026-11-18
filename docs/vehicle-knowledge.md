# Référence véhicule et pannes signalées

Couche de connaissance consultée par le diagnostic IA, séparée des cas atelier (`ExperienceCase`) et des connaissances vérifiées (`KnowledgeItem`).

## Contenu (`data/vehicle_knowledge/`)

- `generations.json` : 746 générations (homologations suisses ASTRA, données ouvertes) avec 5 558 variantes moteur. Pour chaque génération : codes moteur, cylindrée, puissance, couple, boîtes, préfixes VIN, emplacement du code moteur et numéros d'homologation UE.
- `reported_issues.json` : pannes déjà arrivées en conditions réelles (702 générations sur 746 ont des cas officiels ou des plaintes).

| Origine | Nombre | Rattachement | Classe de confiance |
|---|---|---|---|
| Recherche web sourcée (`web_research`) | 87 pannes connues | périmètre : code moteur, marque, modèle, carburant, cylindrée, boîte, années | signal web |
| Safety Gate UE (`safety_gate`) | 2 870 rappels | numéro d'homologation UE, sinon modèle + dates de production | autorité |
| RappelConso FR (`rappelconso`) | 464 rappels | modèle + années | autorité |
| Rappels NHTSA US (`nhtsa_recall`) | 2 098 rappels, avec références de pièces | modèle + années | autorité |
| Bulletins NHTSA US (`nhtsa_tsb`) | 4 291 bulletins citant 1 à 8 codes défaut | modèle + années | constructeur |
| Plaintes de propriétaires NHTSA (`nhtsa_complaints`) | 4 337 motifs, soit 217 354 plaintes | modèle + année-modèle (série pour BMW) | signal de terrain |

Les plaintes sont regroupées par génération et par motif (58 motifs : chaîne, pompe à eau, consommation d'huile, boîte double embrayage…). Chaque motif donne le nombre de cas, le kilométrage médian, la répartition par année, les codes défaut cités et les pannes associées. Aucune donnée personnelle n'est conservée (ni texte, ni VIN, ni ville).

## Fonctionnement

- Tables : `vehicle_generations`, `engine_variants`, `reported_vehicle_issues`, `reported_issue_generations` (migration `0015`).
- Chargement : `seed.py` appelle `vehicle_knowledge.load_reference_data`. Le rechargement n'a lieu que si la somme de contrôle des fichiers a changé (environ 3 s).
- Diagnostic : `context_builder` ajoute `vehicle_reference` et `reported_vehicle_issues`. Ces dernières deviennent des extraits citables (`origin = orvect_reported_issues`, `verified = false`). Le prompt s'en sert pour classer les hypothèses et choisir les contrôles, jamais comme preuve.
- Classement : le score part du niveau de preuve (rappel > bulletin > presse > site spécialisé > forum > plaintes), puis tient compte des codes défaut communs (pondérés par leur spécificité), des mots de symptôme communs et, pour les plaintes, du nombre de cas (log10, plafonné).
- Filtrage :
  - un rappel sans rapport avec les symptômes est rétrogradé ;
  - un motif de plaintes sans rapport avec les symptômes saisis est écarté ;
  - un motif « diesel » n'apparaît pas sur une variante essence connue.
- Les textes officiels anglais (NHTSA, Safety Gate) reçoivent des étiquettes françaises (même lexique que les plaintes) pour pouvoir être recoupés avec les symptômes.
- API : `POST /api/vehicle-knowledge/lookup` (VIN, marque, modèle, année, code moteur, codes défaut, symptômes). L'appel est en POST pour que le VIN n'apparaisse dans aucune URL ; seuls ses 11 premiers caractères sont comparés.

## Mise à jour

Le pipeline se trouve dans `donnees-pieces/connaissance/` (voir son README). Après reconstruction, relancer le seed : le rechargement se déclenche tout seul.
