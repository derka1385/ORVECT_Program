# Collecte de cas atelier ORVECT

Page statique et anonyme publiée sous `/collecte/`. Elle ne demande ni atelier, ni technicien, ni e-mail, ni donnée d’identification du client. Elle fonctionne sans compte ni secret exposé : le navigateur sauvegarde le brouillon localement et génère deux exports complémentaires, un TXT lisible et un JSON structuré. Sur iPhone, la feuille de partage permet de les envoyer par Mail ou AirDrop ; ailleurs, les deux fichiers sont téléchargés et un e-mail ORVECT prérempli s’ouvre.

Les exports reçus peuvent être regroupés sur le Mac avec :

```bash
python3 scripts/compile_workshop_cases.py /chemin/vers/les/json --output orvect-workshop-cases
```

La commande produit un fichier JSONL adapté aux traitements IA et un CSV ouvrable dans Excel. Le formulaire exclut volontairement VIN, plaque et identité client.
