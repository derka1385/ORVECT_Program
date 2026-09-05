# Identification du véhicule

Un VIN décrit l’identité de construction, pas nécessairement le logiciel, la calibration ou toutes les variantes électroniques. DiagPilot conserve donc les données fournisseur comme candidates et exige une confirmation humaine.

Les champs critiques sont marque, modèle, année, marché, code moteur et transmission. La précision déterministe progresse de `unknown` à `basic_vehicle`, `model_specific`, `engine_specific`, `variant_specific`, `ecu_specific`, puis `verified_documentation`. Un conflit ECU fait redescendre le niveau à `unknown` et place la résolution en `conflict`.

Chaque valeur garde sa provenance et sa confiance. Une correction crée une provenance `technician_confirmation`; elle ne modifie pas silencieusement la réponse initiale.
