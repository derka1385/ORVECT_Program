window.ORVECT_INVESTOR_CASES = [
  {
    "title": "Golf VII · ratés et circuit d’allumage",
    "synthetic": true,
    "vehicle_id": "00000000-0000-0000-0000-000000000007",
    "mileage": 86420,
    "symptoms": "DÉMONSTRATION SYNTHÉTIQUE. Ralenti irrégulier, vibrations et voyant moteur. Les ratés observés se concentrent sur le cylindre 1. Aucun contrôle de composant n’a encore été effectué.",
    "circumstances": "Scénario simulé : moteur à température de fonctionnement, véhicule immobilisé dans l’atelier. Symptômes intermittents au ralenti.",
    "fault_codes": [
      {
        "code": "P0301",
        "namespace": "sae_obd2",
        "ecu": "ECU moteur",
        "status": "active",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Code préenregistré du scénario synthétique, à relire avant analyse."
      },
      {
        "code": "P0351",
        "namespace": "sae_obd2",
        "ecu": "ECU moteur",
        "status": "intermittent",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Code préenregistré du scénario synthétique, à relire avant analyse."
      }
    ],
    "measurements": [
      {
        "name": "Compteur de ratés cylindre 1",
        "value": 38,
        "unit": "événements / 60 s",
        "conditions": "Relevé synthétique au ralenti sur 60 secondes",
        "source": "manual"
      },
      {
        "name": "Compteur de ratés cylindres 2, 3 et 4",
        "value": 0,
        "unit": "événements / 60 s",
        "conditions": "Même fenêtre simulée de 60 secondes",
        "source": "manual"
      },
      {
        "name": "Tension batterie",
        "value": 13.9,
        "unit": "V",
        "conditions": "Mesure synthétique moteur tournant au ralenti ; aucune valeur constructeur de référence fournie",
        "source": "manual"
      }
    ],
    "id": "golf-misfire",
    "summary": "P0301 + P0351 · ralenti irrégulier · trois relevés. Explorer un dossier avant tout contrôle."
  },
  {
    "title": "Golf VII · observation complémentaire",
    "synthetic": true,
    "vehicle_id": "00000000-0000-0000-0000-000000000007",
    "mileage": 86420,
    "symptoms": "DÉMONSTRATION SYNTHÉTIQUE. Ralenti irrégulier, vibrations et voyant moteur. Les ratés observés se concentrent sur le cylindre 1. SIMULATION : une inspection visuelle signale un verrou de connecteur cassé ; aucune réparation ni confirmation de cause.",
    "circumstances": "Scénario simulé : moteur à température de fonctionnement, véhicule immobilisé dans l’atelier. Symptômes intermittents au ralenti.",
    "fault_codes": [
      {
        "code": "P0301",
        "namespace": "sae_obd2",
        "ecu": "ECU moteur",
        "status": "active",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Code préenregistré du scénario synthétique, à relire avant analyse."
      },
      {
        "code": "P0351",
        "namespace": "sae_obd2",
        "ecu": "ECU moteur",
        "status": "intermittent",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Code préenregistré du scénario synthétique, à relire avant analyse."
      }
    ],
    "measurements": [
      {
        "name": "Compteur de ratés cylindre 1",
        "value": 38,
        "unit": "événements / 60 s",
        "conditions": "Relevé synthétique au ralenti sur 60 secondes",
        "source": "manual"
      },
      {
        "name": "Compteur de ratés cylindres 2, 3 et 4",
        "value": 0,
        "unit": "événements / 60 s",
        "conditions": "Même fenêtre simulée de 60 secondes",
        "source": "manual"
      },
      {
        "name": "Tension batterie",
        "value": 13.9,
        "unit": "V",
        "conditions": "Mesure synthétique moteur tournant au ralenti ; aucune valeur constructeur de référence fournie",
        "source": "manual"
      },
      {
        "name": "Inspection visuelle connecteur bobine cylindre 1",
        "value": "SIMULATION : verrou cassé, connecteur partiellement débranché ; aucun remplacement effectué",
        "unit": "",
        "conditions": "Observation synthétique contact coupé, moteur refroidi",
        "source": "manual"
      }
    ],
    "id": "golf-connector",
    "summary": "Même contexte, avec une observation du connecteur. Comparer les résultats sans conclure automatiquement à une pièce défectueuse."
  },
  {
    "title": "Golf VII · définition manquante",
    "synthetic": true,
    "vehicle_id": "00000000-0000-0000-0000-000000000007",
    "mileage": 86420,
    "symptoms": "DÉMONSTRATION SYNTHÉTIQUE. Voyant moteur signalé. Aucun relevé complémentaire et aucune définition constructeur validée disponibles.",
    "circumstances": "Scénario fictif de données insuffisantes. Aucune interprétation constructeur ne doit être déduite du code seul.",
    "fault_codes": [
      {
        "code": "P1351",
        "namespace": "vag_obd",
        "ecu": "ECU moteur",
        "status": "unknown",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Code synthétique relu ; sa présence ne confirme aucune définition constructeur."
      }
    ],
    "measurements": [],
    "id": "golf-unknown",
    "summary": "P1351 · code constructeur non documenté. Montrer comment le prototype explicite ses limites."
  }
];

window.ORVECT_INVESTOR_CASES_DE = {
  "golf-misfire": {
    "title": "Golf VII · Fehlzündungen und Zündstromkreis",
    "symptoms": "SYNTHETISCHE DEMONSTRATION. Unruhiger Leerlauf, Vibrationen und Motorkontrollleuchte. Die beobachteten Fehlzündungen konzentrieren sich auf Zylinder 1. Es wurde noch kein Bauteil geprüft.",
    "circumstances": "Simuliertes Szenario: Motor auf Betriebstemperatur, Fahrzeug steht in der Werkstatt. Sporadische Symptome im Leerlauf.",
    "measurements": [
      {"name":"Fehlzündungszähler Zylinder 1","unit":"Ereignisse / 60 s"},
      {"name":"Fehlzündungszähler Zylinder 2, 3 und 4","unit":"Ereignisse / 60 s"},
      {"name":"Batteriespannung"}
    ]
  },
  "golf-connector": {
    "title": "Golf VII · zusätzliche Beobachtung",
    "symptoms": "SYNTHETISCHE DEMONSTRATION. Unruhiger Leerlauf, Vibrationen und Motorkontrollleuchte. Die beobachteten Fehlzündungen konzentrieren sich auf Zylinder 1. SIMULATION: Bei einer Sichtprüfung wurde eine gebrochene Steckerverriegelung festgestellt; es erfolgte weder eine Reparatur noch eine Bestätigung der Ursache.",
    "circumstances": "Simuliertes Szenario: Motor auf Betriebstemperatur, Fahrzeug steht in der Werkstatt. Sporadische Symptome im Leerlauf.",
    "measurements": [
      {"name":"Fehlzündungszähler Zylinder 1","unit":"Ereignisse / 60 s"},
      {"name":"Fehlzündungszähler Zylinder 2, 3 und 4","unit":"Ereignisse / 60 s"},
      {"name":"Batteriespannung"},
      {"name":"Sichtprüfung des Zündspulensteckers an Zylinder 1","value":"SIMULATION: Verriegelung gebrochen, Stecker teilweise gelöst; kein Teil ersetzt"}
    ]
  },
  "golf-unknown": {
    "title": "Golf VII · fehlende Definition",
    "symptoms": "SYNTHETISCHE DEMONSTRATION. Motorkontrollleuchte gemeldet. Es liegen keine zusätzlichen Messwerte und keine validierte Herstellerdefinition vor.",
    "circumstances": "Fiktives Szenario mit unzureichenden Daten. Aus dem Code allein darf keine Herstellerinterpretation abgeleitet werden.",
    "measurements": []
  }
};
