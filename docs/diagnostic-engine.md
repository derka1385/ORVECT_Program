# Moteur de diagnostic

Le moteur comporte trois couches indépendantes.

1. **Normalisation** : DTC en majuscules, mesures structurées, véhicule et observations dans un contexte canonique.
2. **Règles** : récupération des causes et procédures compatibles, classement initial, sélection de la prochaine étape puis ajustements explicables à chaque résultat.
3. **IA** : synthèse uniquement des éléments autorisés. `LLMProvider` est abstrait et `MockLLMProvider` fonctionne hors ligne. Le schéma `AIAnalysisOutput` interdit les champs inattendus.

## Scénario P0301

La première étape consiste à permuter les bobines 1 et 2 après mise hors tension et refroidissement. `fault_moved_to_cylinder_2` renforce la bobine et propose une confirmation électrique/visuelle. `fault_stayed_on_cylinder_1` affaiblit cette hypothèse et poursuit vers bougie, injecteur puis étanchéité. Les scores servent uniquement au classement et ne représentent pas une probabilité scientifique.

Le moteur ne conclut jamais qu’une pièce est défectueuse depuis le DTC seul. Toute étape inclut limites, avertissements et identifiants de source.

## Parcours générique

Tout code respectant le format `[PBCU][0-9A-F]{4}` peut ouvrir une session. Si une définition existe dans le catalogue, elle est affichée avec sa source puis le moteur demande de confirmer statut, calculateur, données figées et applicabilité au véhicule. Si aucune définition générique n’existe, comme pour un code potentiellement constructeur tel que P1351, le moteur n’attribue aucun composant : il demande l’identification précise du véhicule et une documentation autorisée. Le parcours peut être clôturé en état non résolu. Une règle spécifique n’est créée qu’après validation de connaissances applicables.
