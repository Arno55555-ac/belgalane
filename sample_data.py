"""Données de démonstration de BELGALANE, tirées du cahier des charges.

Le mode démo les charge automatiquement : aucune IA n'est appelée,
rien n'est consommé. Les dates sont au format AAAA-MM-JJ.
"""

# Factures d'achat, telles que l'IA devrait les extraire.
# GERVAIS et AIR LIQUIDE sont importées deux fois dans le cahier des charges : l'app
# retire ces doublons au chargement. La facture SNCF n'indique ni HT ni TVA :
# ces valeurs sont donc à None (null), on ne les invente pas.
FACTURES_DEMO = [
    {"date": "2019-03-12", "fournisseur": "TOTAL", "montant_ttc": 78.28,
     "montant_ht": 65.23, "tva": 13.05, "type_depense": "Essence",
     "fichier": "Facture TOTAL.pdf"},
    {"date": "2019-03-26", "fournisseur": "OFFICE DEPOT", "montant_ttc": 307.34,
     "montant_ht": 256.12, "tva": 51.22, "type_depense": "Fournitures bureau",
     "fichier": "Facture OFFICE DEPOT.pdf"},
    {"date": "2019-04-15", "fournisseur": "FNAC", "montant_ttc": 39.00,
     "montant_ht": 32.50, "tva": 6.50, "type_depense": "Matériel informatique",
     "fichier": "Facture FNAC.pdf"},
    {"date": "2019-04-24", "fournisseur": "AIR FRANCE", "montant_ttc": 658.30,
     "montant_ht": 658.30, "tva": 0.00, "type_depense": "Déplacement",
     "fichier": "Facture AIR FRANCE.pdf"},
    {"date": "2019-05-02", "fournisseur": "SNCF", "montant_ttc": 62.00,
     "montant_ht": None, "tva": None, "type_depense": "Déplacement",
     "fichier": "Billet SNCF.pdf"},
    {"date": "2019-06-25", "fournisseur": "UBER", "montant_ttc": 30.36,
     "montant_ht": 25.30, "tva": 5.06, "type_depense": "Déplacement",
     "fichier": "Facture UBER.pdf"},
    {"date": "2019-07-08", "fournisseur": "GERVAIS", "montant_ttc": 1830.00,
     "montant_ht": 1525.00, "tva": 305.00, "type_depense": "Marchandises",
     "fichier": "Facture GERVAIS.pdf"},
    {"date": "2019-07-08", "fournisseur": "GERVAIS", "montant_ttc": 1830.00,
     "montant_ht": 1525.00, "tva": 305.00, "type_depense": "Marchandises",
     "fichier": "Facture GERVAIS (1).pdf"},
    {"date": "2019-07-15", "fournisseur": "LEON", "montant_ttc": 82.75,
     "montant_ht": 75.23, "tva": 7.52, "type_depense": "Restaurant",
     "fichier": "Facture LEON.pdf"},
    {"date": "2019-07-17", "fournisseur": "AIR LIQUIDE", "montant_ttc": 10500.00,
     "montant_ht": 8750.00, "tva": 1750.00, "type_depense": "Marchandises",
     "fichier": "Facture AIR LIQUIDE.pdf"},
    {"date": "2019-07-17", "fournisseur": "AIR LIQUIDE", "montant_ttc": 10500.00,
     "montant_ht": 8750.00, "tva": 1750.00, "type_depense": "Marchandises",
     "fichier": "Facture AIR LIQUIDE copie.pdf"},
]

# Relevé de banque CIC. Les types d'opération sont corrigés par rapport
# au cahier des charges : AIR LIQUIDE et GERVAIS sont des FOURNISSEURS,
# l'apport de trésorerie est AUTRE.
# Contrôle : 5 000 + 13 600 (crédits) - 17 879,92 (débits) = 720,08.
RELEVE_BANCAIRE_DEMO = {
    "banque": "CIC",
    "fichier": "RELEVE CIC 07 2019.pdf",
    "solde_debut": 5000.00,
    "solde_fin": 720.08,
    "operations": [
        {"date": "2019-03-02", "libelle": "BAT MAN", "debit": None,
         "credit": 1200.00, "type_operation": "CLIENT"},
        {"date": "2019-03-10", "libelle": "SPIDER MAN", "debit": None,
         "credit": 2400.00, "type_operation": "CLIENT"},
        {"date": "2019-03-12", "libelle": "TOTAL", "debit": 78.28,
         "credit": None, "type_operation": "FOURNISSEUR"},
        {"date": "2019-03-26", "libelle": "OFFICE DEPOT", "debit": 307.34,
         "credit": None, "type_operation": "FOURNISSEUR"},
        {"date": "2019-04-14", "libelle": "URSSAF", "debit": 2345.00,
         "credit": None, "type_operation": "AUTRE"},
        {"date": "2019-04-15", "libelle": "MAC DO", "debit": 21.00,
         "credit": None, "type_operation": "FOURNISSEUR"},
        {"date": "2019-04-15", "libelle": "FNAC", "debit": 39.00,
         "credit": None, "type_operation": "FOURNISSEUR"},
        {"date": "2019-04-24", "libelle": "AIR FRANCE", "debit": 658.30,
         "credit": None, "type_operation": "FOURNISSEUR"},
        {"date": "2019-05-02", "libelle": "SNCF", "debit": 62.00,
         "credit": None, "type_operation": "FOURNISSEUR"},
        {"date": "2019-06-01", "libelle": "FRAIS DE BANQUE", "debit": 39.00,
         "credit": None, "type_operation": "AUTRE"},
        {"date": "2019-06-30", "libelle": "APPORT DE TRESORERIE", "debit": None,
         "credit": 10000.00, "type_operation": "AUTRE"},
        {"date": "2019-07-08", "libelle": "GERVAIS", "debit": 1830.00,
         "credit": None, "type_operation": "FOURNISSEUR"},
        {"date": "2019-07-08", "libelle": "SALAIRE", "debit": 2000.00,
         "credit": None, "type_operation": "AUTRE"},
        {"date": "2019-07-17", "libelle": "AIR LIQUIDE", "debit": 10500.00,
         "credit": None, "type_operation": "FOURNISSEUR"},
    ],
}

# Factures de vente d'exemple, inventées pour la démo : le cahier des charges ne
# prévoit pas de ventes. BAT MAN est retrouvée en banque (encaissement du 2019-03-02),
# WONDER WOMAN n'est pas encaissée, et l'encaissement de SPIDER MAN n'a pas de facture.
VENTES_DEMO = [
    {"date": "2019-03-01", "client": "BAT MAN", "montant_ttc": 1200.00,
     "montant_ht": 1000.00, "tva": 200.00, "numero_facture": "FA-2019-001",
     "fichier": "Facture FA-2019-001.pdf"},
    {"date": "2019-06-15", "client": "WONDER WOMAN", "montant_ttc": 960.00,
     "montant_ht": 800.00, "tva": 160.00, "numero_facture": "FA-2019-002",
     "fichier": "Facture FA-2019-002.pdf"},
]
