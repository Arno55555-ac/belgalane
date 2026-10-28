"""Sauvegarde des factures, des relevés de banque et de leurs justificatifs (relevés de
carte, de LCR, bordereaux de remise de chèques) dans une base SQLite (un seul fichier).

Les données survivent ainsi au rechargement de la page et au redémarrage de l'app.
Seules les données lues par l'IA sont enregistrées : les doublons et les
rapprochements sont recalculés à chaque affichage (voir traitement.py).

Le fichier est créé à côté du code, dans donnees/. Il contient des données
financières : il ne doit jamais être publié (voir .gitignore).
"""

import sqlite3
from contextlib import closing
from pathlib import Path

CHEMIN = Path(__file__).parent / "donnees" / "belgalane.db"

COLONNES_FACTURE = ["date", "fournisseur", "montant_ttc", "montant_ht", "tva",
                    "type_depense", "fichier"]
COLONNES_VENTE = ["date", "client", "montant_ttc", "montant_ht", "tva",
                  "numero_facture", "fichier"]
COLONNES_OPERATION = ["date", "libelle", "debit", "credit", "type_operation"]

# Un relevé de banque, un relevé de carte, un relevé de LCR et un bordereau de remise ont
# la même forme : une ligne dans leur table (rangées dans l'ordre des dates) et leurs
# opérations dans une seconde table, chacune portant le numéro (0, 1, 2…) du relevé
# auquel elle appartient. Pour chaque sorte : (table, colonnes, table des opérations,
# colonnes des opérations, colonne du numéro).
RELEVES = ("releve", ["banque", "fichier", "solde_debut", "solde_fin"],
           "operations", COLONNES_OPERATION, "releve_no")
CARTES = ("cartes", ["fichier", "date_arrete", "date_prelevement", "total_net"],
          "operations_carte", COLONNES_OPERATION, "carte_no")
LCRS = ("lcr", ["fichier", "numero", "date_reglement", "total", "total_refuse"],
        "operations_lcr",
        COLONNES_OPERATION + ["reference", "type_effet", "numero_effet", "montant_refuse"],
        "lcr_no")
REMISES = ("remises", ["fichier", "numero", "date", "total"],
           "operations_remise", COLONNES_OPERATION + ["banque"], "remise_no")

SCHEMA = """
CREATE TABLE IF NOT EXISTS factures (
    id INTEGER PRIMARY KEY, date TEXT, fournisseur TEXT, montant_ttc REAL,
    montant_ht REAL, tva REAL, type_depense TEXT, fichier TEXT);
CREATE TABLE IF NOT EXISTS ventes (
    id INTEGER PRIMARY KEY, date TEXT, client TEXT, montant_ttc REAL,
    montant_ht REAL, tva REAL, numero_facture TEXT, fichier TEXT);
CREATE TABLE IF NOT EXISTS releve (
    banque TEXT, fichier TEXT, solde_debut REAL, solde_fin REAL);
CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY, date TEXT, libelle TEXT, debit REAL, credit REAL,
    type_operation TEXT, releve_no INTEGER);
CREATE TABLE IF NOT EXISTS cartes (
    fichier TEXT, date_arrete TEXT, date_prelevement TEXT, total_net REAL);
CREATE TABLE IF NOT EXISTS operations_carte (
    id INTEGER PRIMARY KEY, date TEXT, libelle TEXT, debit REAL, credit REAL,
    type_operation TEXT, carte_no INTEGER);
CREATE TABLE IF NOT EXISTS lcr (
    fichier TEXT, numero TEXT, date_reglement TEXT, total REAL, total_refuse REAL);
CREATE TABLE IF NOT EXISTS operations_lcr (
    id INTEGER PRIMARY KEY, date TEXT, libelle TEXT, debit REAL, credit REAL,
    type_operation TEXT, reference TEXT, type_effet TEXT, numero_effet TEXT,
    montant_refuse REAL, lcr_no INTEGER);
CREATE TABLE IF NOT EXISTS remises (
    fichier TEXT, numero TEXT, date TEXT, total REAL);
CREATE TABLE IF NOT EXISTS operations_remise (
    id INTEGER PRIMARY KEY, date TEXT, libelle TEXT, debit REAL, credit REAL,
    type_operation TEXT, banque TEXT, remise_no INTEGER);
"""


def _connexion():
    CHEMIN.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CHEMIN)
    con.executescript(SCHEMA)
    # Base créée avant la gestion de plusieurs relevés : ses opérations appartiennent
    # à l'unique relevé qu'elle contient.
    colonnes = [ligne[1] for ligne in con.execute("PRAGMA table_info(operations)")]
    if "releve_no" not in colonnes:
        con.execute("ALTER TABLE operations ADD COLUMN releve_no INTEGER")
        con.execute("UPDATE operations SET releve_no = 0")
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version < 2:
        con.execute("PRAGMA user_version = 2")  # version du schéma, pour de futures évolutions
    con.commit()
    return con


def _lire(con, table, colonnes):
    lignes = con.execute(f"SELECT {', '.join(colonnes)} FROM {table} ORDER BY rowid")
    return [dict(zip(colonnes, ligne)) for ligne in lignes]


def _lire_releves(con, sorte):
    table, colonnes, table_operations, colonnes_operations, cle_no = sorte
    releves = _lire(con, table, colonnes)
    operations = _lire(con, table_operations, colonnes_operations + [cle_no])
    for numero, releve in enumerate(releves):
        releve["operations"] = [
            {c: op[c] for c in colonnes_operations}
            for op in operations if op[cle_no] == numero]
    return releves


def charger():
    """Renvoie (factures, ventes, relevés, relevés de carte, relevés de LCR, bordereaux
    de remise) tels qu'ils ont été enregistrés. Chacun est une liste, vide s'il n'y en a
    pas."""
    with closing(_connexion()) as con:
        return (_lire(con, "factures", COLONNES_FACTURE),
                _lire(con, "ventes", COLONNES_VENTE),
                _lire_releves(con, RELEVES), _lire_releves(con, CARTES),
                _lire_releves(con, LCRS), _lire_releves(con, REMISES))


def _ecrire(con, table, colonnes, lignes):
    marques = ", ".join("?" for _ in colonnes)
    con.executemany(f"INSERT INTO {table} ({', '.join(colonnes)}) VALUES ({marques})",
                    [[ligne.get(c) for c in colonnes] for ligne in lignes])


def _ecrire_releves(con, sorte, releves):
    table, colonnes, table_operations, colonnes_operations, cle_no = sorte
    _ecrire(con, table, colonnes, releves)
    for numero, releve in enumerate(releves):
        _ecrire(con, table_operations, colonnes_operations + [cle_no],
                [{**op, cle_no: numero} for op in releve["operations"]])


def sauvegarder(factures, ventes, releves, cartes, lcrs, remises):
    """Remplace tout le contenu de la base par les données données.
    Tout ou rien : en cas d'erreur, la base garde son contenu précédent."""
    with closing(_connexion()) as con, con:
        for table in ("factures", "ventes", "releve", "operations", "cartes",
                      "operations_carte", "lcr", "operations_lcr", "remises",
                      "operations_remise"):
            con.execute(f"DELETE FROM {table}")
        _ecrire(con, "factures", COLONNES_FACTURE, factures)
        _ecrire(con, "ventes", COLONNES_VENTE, ventes)
        _ecrire_releves(con, RELEVES, releves)
        _ecrire_releves(con, CARTES, cartes)
        _ecrire_releves(con, LCRS, lcrs)
        _ecrire_releves(con, REMISES, remises)
