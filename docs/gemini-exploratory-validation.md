# Vérification Gemini exploratoire — 8 septembre 2026

Cinq scénarios synthétiques validés avec gemini-3.5-flash. Le premier essai multi-code a subi une indisponibilité temporaire du fournisseur ; sa reprise et la réévaluation ont réussi.

| Codes | Hypothèses | Résultat local |
|---|---:|---|
| P0171 | 3 | [Ouvrir](http://127.0.0.1:3000/diagnostics/ai/e9180ced-ec08-4137-91e8-e26bc6532bb5) |
| P1351 | 2 | [Ouvrir](http://127.0.0.1:3000/diagnostics/ai/720aed4a-a95a-41f1-8b2b-a19d28e469d2) |
| U0100 | 2 | [Ouvrir](http://127.0.0.1:3000/diagnostics/ai/257805ee-b4a2-4342-a682-6afc15143abb) |
| P1FFF | 2 | [Ouvrir](http://127.0.0.1:3000/diagnostics/ai/88a1a82e-9348-4a24-aa74-efe41a4d5fae) |
| P0301+P0351 | 2 | [Ouvrir](http://127.0.0.1:3000/diagnostics/ai/8cd543bf-77ac-4b6d-a332-81b7f118c477) |

La nouvelle observation du connecteur a modifié les hypothèses du cas P0301 + P0351. Tous les éléments exploratoires sont non vérifiés, et la décision de sécurité provient toujours du Safety Engine.

Validation : 52 tests ciblés avant la correction de longueur du prompt, puis 8 tests exploratoires après ajout de la régression sur la taille du champ en base. TypeScript et compilation Docker réussis.

Cela prouve le fonctionnement sur ces scénarios, pas l’exactitude de tous les codes ni la disponibilité permanente du fournisseur. GitHub Pages reste une simulation statique sans Gemini.
