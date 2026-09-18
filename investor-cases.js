window.ORVECT_INVESTOR_CASES = [
  {
    "id": "golf-p0301-epc",
    "title": "Golf VII 1.4 TSI · P0301 + EPC",
    "synthetic": true,
    "vehicle_id": "00000000-0000-0000-0000-000000000007",
    "vehicle": {
      "make": "Volkswagen",
      "model": "Golf VII",
      "year": "2018",
      "engine": "CZCA",
      "fuel": "Essence",
      "gearbox": "Manuelle",
      "platform": "MQB"
    },
    "mileage": 112000,
    "summary": "P0301 · ralenti irrégulier · voyant EPC intermittent. Le cas de référence Orvect.",
    "symptoms": "Ralenti irrégulier et vibrations à l’arrêt. Voyant EPC qui s’allume par intermittence. Aucun composant n’a encore été contrôlé ou remplacé.",
    "circumstances": "Symptômes plus marqués moteur froid, véhicule immobilisé à l’atelier. Aucune réparation récente signalée par le client.",
    "fault_codes": [
      {
        "code": "P0301",
        "namespace": "sae_obd2",
        "ecu": "ECU moteur",
        "status": "active",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Relevé au scanner puis confirmé par le technicien."
      }
    ],
    "measurements": []
  },
  {
    "id": "golf-multi-dtc",
    "title": "Golf VII 1.4 TSI · trois codes corrélés",
    "synthetic": true,
    "vehicle_id": "00000000-0000-0000-0000-000000000007",
    "vehicle": {
      "make": "Volkswagen",
      "model": "Golf VII",
      "year": "2018",
      "engine": "CZCA",
      "fuel": "Essence",
      "gearbox": "Manuelle",
      "platform": "MQB"
    },
    "mileage": 124500,
    "summary": "P0301 + P0171 + P0507 · rechercher la cause racine commune plutôt que trois explications.",
    "symptoms": "Ralenti instable et anormalement élevé, légère perte de puissance en charge, voyant moteur allumé. Le client signale une consommation en hausse.",
    "circumstances": "Symptômes permanents depuis environ deux semaines. Aucune intervention récente sur le moteur.",
    "fault_codes": [
      {
        "code": "P0301",
        "namespace": "sae_obd2",
        "ecu": "ECU moteur",
        "status": "active",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Relevé au scanner puis confirmé par le technicien."
      },
      {
        "code": "P0171",
        "namespace": "sae_obd2",
        "ecu": "ECU moteur",
        "status": "stored",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Relevé au scanner puis confirmé par le technicien."
      },
      {
        "code": "P0507",
        "namespace": "sae_obd2",
        "ecu": "ECU moteur",
        "status": "active",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Relevé au scanner puis confirmé par le technicien."
      }
    ],
    "measurements": [
      {
        "name": "Régime de ralenti",
        "value": 1150,
        "unit": "tr/min",
        "conditions": "Moteur chaud, sans consommateur électrique",
        "source": "manual"
      },
      {
        "name": "Correction long terme carburant banc 1",
        "value": 18.7,
        "unit": "%",
        "conditions": "Ralenti moteur chaud",
        "source": "manual"
      }
    ]
  },
  {
    "id": "bmw-320d-power-loss",
    "title": "BMW 320d N47 · ralenti et perte de puissance",
    "synthetic": true,
    "vehicle_id": "00000000-0000-0000-0000-000000000008",
    "vehicle": {
      "make": "BMW",
      "model": "320d (F30)",
      "year": "2011",
      "engine": "N47D20C",
      "fuel": "Diesel",
      "gearbox": "Manuelle",
      "platform": "F3x"
    },
    "mileage": 185000,
    "summary": "P0401 · diesel haut kilométrage · vérifier que le raisonnement n’est pas calé sur un seul véhicule.",
    "symptoms": "Ralenti irrégulier et perte de puissance progressive à l’accélération. Fumée noire occasionnelle signalée par le client.",
    "circumstances": "Véhicule diesel à haut kilométrage, usage majoritairement urbain. Symptômes accentués à froid.",
    "fault_codes": [
      {
        "code": "P0401",
        "namespace": "sae_obd2",
        "ecu": "ECU moteur",
        "status": "active",
        "freeze_frame": {},
        "technician_verification": "confirmed",
        "technician_note": "Relevé au scanner puis confirmé par le technicien."
      }
    ],
    "measurements": []
  },
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
  "golf-p0301-epc": {
    "summary": "P0301 · unruhiger Leerlauf · sporadische EPC-Leuchte. Der Orvect-Referenzfall.",
    "title": "Golf VII 1.4 TSI · P0301 + EPC",
    "symptoms": "Unruhiger Leerlauf und Vibrationen im Stand. EPC-Leuchte geht sporadisch an. Bisher wurde kein Bauteil geprüft oder ersetzt.",
    "circumstances": "Symptome bei kaltem Motor deutlicher, Fahrzeug steht in der Werkstatt. Keine kürzliche Reparatur gemeldet.",
    "measurements": []
  },
  "golf-multi-dtc": {
    "summary": "P0301 + P0171 + P0507 · die gemeinsame Grundursache suchen statt drei Erklärungen.",
    "title": "Golf VII 1.4 TSI · drei zusammenhängende Codes",
    "symptoms": "Instabiler und ungewöhnlich hoher Leerlauf, leichter Leistungsverlust unter Last, Motorkontrollleuchte an. Der Kunde meldet einen erhöhten Verbrauch.",
    "circumstances": "Dauerhafte Symptome seit etwa zwei Wochen. Kein kürzlicher Eingriff am Motor.",
    "measurements": [
      {
        "name": "Leerlaufdrehzahl",
        "unit": "U/min"
      },
      {
        "name": "Langzeit-Kraftstoffkorrektur Bank 1",
        "unit": "%"
      }
    ]
  },
  "bmw-320d-power-loss": {
    "summary": "P0401 · Diesel mit hoher Laufleistung · prüfen, dass die Argumentation nicht an ein einziges Fahrzeug gebunden ist.",
    "title": "BMW 320d N47 · Leerlauf und Leistungsverlust",
    "symptoms": "Unruhiger Leerlauf und zunehmender Leistungsverlust beim Beschleunigen. Gelegentlich schwarzer Rauch laut Kunde.",
    "circumstances": "Diesel mit hoher Laufleistung, überwiegend Stadtverkehr. Symptome bei kaltem Motor stärker.",
    "measurements": []
  },
  "golf-misfire": {
    "summary": "P0301 + P0351 · unruhiger Leerlauf · drei Messwerte. Einen Fall vor jeder Prüfung erkunden.",
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
    "summary": "Gleicher Kontext, mit einer Beobachtung am Stecker. Ergebnisse vergleichen, ohne automatisch auf ein defektes Teil zu schließen.",
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
    "summary": "P1351 · nicht dokumentierter Herstellercode. Zeigen, wie der Prototyp seine Grenzen offenlegt.",
    "title": "Golf VII · fehlende Definition",
    "symptoms": "SYNTHETISCHE DEMONSTRATION. Motorkontrollleuchte gemeldet. Es liegen keine zusätzlichen Messwerte und keine validierte Herstellerdefinition vor.",
    "circumstances": "Fiktives Szenario mit unzureichenden Daten. Aus dem Code allein darf keine Herstellerinterpretation abgeleitet werden.",
    "measurements": []
  }
};

window.ORVECT_INVESTOR_CASES_EN = {
  "golf-p0301-epc": {
    "title": "Golf VII 1.4 TSI · P0301 + EPC",
    "summary": "P0301 · rough idle · intermittent EPC light. The Orvect reference case.",
    "symptoms": "Rough idle and vibrations at standstill. EPC light coming on intermittently. No component has been checked or replaced yet.",
    "circumstances": "Symptoms more pronounced with a cold engine, vehicle stationary in the workshop. No recent repair reported by the customer.",
    "measurements": []
  },
  "golf-multi-dtc": {
    "title": "Golf VII 1.4 TSI · three correlated codes",
    "summary": "P0301 + P0171 + P0507 · look for the shared root cause rather than three explanations.",
    "symptoms": "Unstable and abnormally high idle, slight loss of power under load, engine light on. The customer reports higher fuel consumption.",
    "circumstances": "Permanent symptoms for about two weeks. No recent work on the engine.",
    "measurements": [
      {
        "name": "Idle speed",
        "unit": "rpm"
      },
      {
        "name": "Long-term fuel trim bank 1",
        "unit": "%"
      }
    ]
  },
  "bmw-320d-power-loss": {
    "title": "BMW 320d N47 · rough idle and loss of power",
    "summary": "P0401 · high-mileage diesel · check that the reasoning is not tied to a single vehicle.",
    "symptoms": "Rough idle and progressive loss of power when accelerating. Occasional black smoke reported by the customer.",
    "circumstances": "High-mileage diesel, mostly urban use. Symptoms worse when cold.",
    "measurements": []
  },
  "golf-misfire": {
    "title": "Golf VII · misfires and ignition circuit",
    "summary": "P0301 + P0351 · rough idle · three readings. Explore a case before any check.",
    "symptoms": "SYNTHETIC DEMONSTRATION. Rough idle, vibrations and engine light. The observed misfires concentrate on cylinder 1. No component check has been performed yet.",
    "circumstances": "Simulated scenario: engine at operating temperature, vehicle stationary in the workshop. Intermittent symptoms at idle.",
    "measurements": [
      {
        "name": "Misfire counter cylinder 1",
        "unit": "events / 60 s"
      },
      {
        "name": "Misfire counter cylinders 2, 3 and 4",
        "unit": "events / 60 s"
      },
      {
        "name": "Battery voltage"
      }
    ]
  },
  "golf-connector": {
    "title": "Golf VII · additional observation",
    "summary": "Same context, with a connector observation. Compare the results without automatically concluding a faulty part.",
    "symptoms": "SYNTHETIC DEMONSTRATION. Rough idle, vibrations and engine light. The observed misfires concentrate on cylinder 1. SIMULATION: a visual inspection reports a broken connector lock; no repair and no confirmed cause.",
    "circumstances": "Simulated scenario: engine at operating temperature, vehicle stationary in the workshop. Intermittent symptoms at idle.",
    "measurements": [
      {
        "name": "Misfire counter cylinder 1",
        "unit": "events / 60 s"
      },
      {
        "name": "Misfire counter cylinders 2, 3 and 4",
        "unit": "events / 60 s"
      },
      {
        "name": "Battery voltage"
      },
      {
        "name": "Visual inspection of the cylinder 1 coil connector",
        "value": "SIMULATION: broken lock, connector partially unplugged; no part replaced"
      }
    ]
  },
  "golf-unknown": {
    "title": "Golf VII · missing definition",
    "summary": "P1351 · undocumented manufacturer code. Show how the prototype makes its limits explicit.",
    "symptoms": "SYNTHETIC DEMONSTRATION. Engine light reported. No additional reading and no validated manufacturer definition available.",
    "circumstances": "Fictional insufficient-data scenario. No manufacturer interpretation may be inferred from the code alone.",
    "measurements": []
  }
};

window.ORVECT_INVESTOR_CASES_SV = {
  "golf-p0301-epc": {
    "title": "Golf VII 1.4 TSI · P0301 + EPC",
    "summary": "P0301 · ojämn tomgång · EPC-lampa som tänds intermittent. Orvects referensfall.",
    "symptoms": "Ojämn tomgång och vibrationer vid stillastående. EPC-lampan tänds intermittent. Ingen komponent har kontrollerats eller bytts ännu.",
    "circumstances": "Symtomen är tydligare med kall motor, fordonet står i verkstaden. Ingen nyligen utförd reparation rapporterad av kunden.",
    "measurements": []
  },
  "golf-multi-dtc": {
    "title": "Golf VII 1.4 TSI · tre samhörande koder",
    "summary": "P0301 + P0171 + P0507 · sök den gemensamma grundorsaken i stället för tre förklaringar.",
    "symptoms": "Instabil och onormalt hög tomgång, lätt effektförlust under belastning, motorlampa tänd. Kunden rapporterar ökad bränsleförbrukning.",
    "circumstances": "Permanenta symtom sedan ungefär två veckor. Inget nyligen utfört arbete på motorn.",
    "measurements": [
      {
        "name": "Tomgångsvarvtal",
        "unit": "varv/min"
      },
      {
        "name": "Långtids bränsletrim bank 1",
        "unit": "%"
      }
    ]
  },
  "bmw-320d-power-loss": {
    "title": "BMW 320d N47 · ojämn tomgång och effektförlust",
    "summary": "P0401 · diesel med hög mätarställning · kontrollera att resonemanget inte är låst till ett enda fordon.",
    "symptoms": "Ojämn tomgång och gradvis effektförlust vid acceleration. Tillfällig svart rök rapporterad av kunden.",
    "circumstances": "Diesel med hög mätarställning, mest stadskörning. Symtomen förvärras vid kall motor.",
    "measurements": []
  },
  "golf-misfire": {
    "title": "Golf VII · misständningar och tändkrets",
    "summary": "P0301 + P0351 · ojämn tomgång · tre avläsningar. Utforska ett ärende före någon kontroll.",
    "symptoms": "SYNTETISK DEMONSTRATION. Ojämn tomgång, vibrationer och motorlampa. De observerade misständningarna koncentreras till cylinder 1. Ingen komponentkontroll har utförts ännu.",
    "circumstances": "Simulerat scenario: motor vid arbetstemperatur, fordonet står i verkstaden. Intermittenta symtom på tomgång.",
    "measurements": [
      {
        "name": "Misständningsräknare cylinder 1",
        "unit": "händelser / 60 s"
      },
      {
        "name": "Misständningsräknare cylinder 2, 3 och 4",
        "unit": "händelser / 60 s"
      },
      {
        "name": "Batterispänning"
      }
    ]
  },
  "golf-connector": {
    "title": "Golf VII · kompletterande observation",
    "summary": "Samma kontext, med en observation av kontakten. Jämför resultaten utan att automatiskt dra slutsatsen om en felaktig del.",
    "symptoms": "SYNTETISK DEMONSTRATION. Ojämn tomgång, vibrationer och motorlampa. De observerade misständningarna koncentreras till cylinder 1. SIMULERING: en visuell inspektion visar en bruten kontaktlåsning; ingen reparation och ingen bekräftad orsak.",
    "circumstances": "Simulerat scenario: motor vid arbetstemperatur, fordonet står i verkstaden. Intermittenta symtom på tomgång.",
    "measurements": [
      {
        "name": "Misständningsräknare cylinder 1",
        "unit": "händelser / 60 s"
      },
      {
        "name": "Misständningsräknare cylinder 2, 3 och 4",
        "unit": "händelser / 60 s"
      },
      {
        "name": "Batterispänning"
      },
      {
        "name": "Visuell inspektion av tändspolens kontakt cylinder 1",
        "value": "SIMULERING: bruten låsning, kontakten delvis urkopplad; ingen del bytt"
      }
    ]
  },
  "golf-unknown": {
    "title": "Golf VII · saknad definition",
    "summary": "P1351 · odokumenterad tillverkarkod. Visa hur prototypen tydliggör sina gränser.",
    "symptoms": "SYNTETISK DEMONSTRATION. Motorlampa rapporterad. Ingen ytterligare avläsning och ingen validerad tillverkardefinition tillgänglig.",
    "circumstances": "Fiktivt scenario med otillräckliga data. Ingen tillverkartolkning får härledas från koden ensam.",
    "measurements": []
  }
};
