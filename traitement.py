"""Logique de BELGALANE : doublons, rapprochement, contrôle de solde, tableaux.

Tout ici est du calcul exact fait par Python. L'IA n'intervient pas :
elle se contente de lire les PDF (voir ia.py).
"""

from datetime import date

import pandas as pd

# Écart maximal, en jours, entre la date d'une facture et son paiement.
TOLERANCE_JOURS = 15

# Compte comptable proposé selon le type de dépense (plan comptable général).
COMPTES = {
    "Essence": "606100",
    "Fournitures bureau": "606400",
    "Matériel informatique": "606400",
    "Déplacement": "625100",
    "Restaurant": "625700",
    "Marchandises": "607000",
}
COMPTE_ATTENTE = "471000"


def _en_date(texte):
    try:
        return date.fromisoformat(texte)
    except (TypeError, ValueError):
        return None


def _format_date(texte):
    d = _en_date(texte)
    return d.strftime("%d/%m/%Y") if d else texte


def marquer_doublons(factures):
    """Une facture est un doublon si une précédente a le même fournisseur,
    la même date et le même montant TTC."""
    deja_vues = set()
    for f in factures:
        cle = ((f.get("fournisseur") or "").upper().strip(),
               f.get("date"), f.get("montant_ttc"))
        f["doublon"] = cle in deja_vues
        deja_vues.add(cle)


def rapprocher(factures, operations):
    """Associe chaque débit fournisseur du relevé à une facture de même
    montant TTC, à TOLERANCE_JOURS près, en prenant la date la plus proche."""
    for f in factures:
        f["retrouve"] = False
    for op in operations:
        op["facture"] = None

    for op in operations:
        if op.get("type_operation") != "FOURNISSEUR" or not op.get("debit"):
            continue
        date_op = _en_date(op.get("date"))
        meilleure, meilleur_ecart = None, None
        for f in factures:
            if f["doublon"] or f["retrouve"] or f.get("montant_ttc") is None:
                continue
            if abs(f["montant_ttc"] - op["debit"]) > 0.01:
                continue
            date_f = _en_date(f.get("date"))
            ecart = abs((date_f - date_op).days) if date_f and date_op else TOLERANCE_JOURS
            if ecart > TOLERANCE_JOURS:
                continue
            if meilleure is None or ecart < meilleur_ecart:
                meilleure, meilleur_ecart = f, ecart
        if meilleure:
            meilleure["retrouve"] = True
            op["facture"] = meilleure


def controle_solde(releve):
    """Renvoie (solde calculé, écart avec le solde de fin lu sur le relevé)."""
    credits = sum(op.get("credit") or 0 for op in releve["operations"])
    debits = sum(op.get("debit") or 0 for op in releve["operations"])
    calcule = round(releve["solde_debut"] + credits - debits, 2)
    return calcule, round(releve["solde_fin"] - calcule, 2)


def statut_facture(f, releve_present):
    if f["doublon"]:
        return "DOUBLON"
    if not releve_present:
        return "NON (pas de relevé)"
    return "OUI" if f["retrouve"] else "NON"


def tableau_achats(factures, releve_present):
    lignes = [{
        "Date": _format_date(f.get("date")),
        "Montant TTC": f.get("montant_ttc"),
        "Montant HT": f.get("montant_ht"),
        "TVA": f.get("tva"),
        "Fournisseur": f.get("fournisseur"),
        "Fichier": f.get("fichier"),
        "Type de dépense": f.get("type_depense"),
        "Retrouvé en banque": statut_facture(f, releve_present),
    } for f in factures]
    return pd.DataFrame(lignes)


def tableau_banque(releve):
    lignes = []
    for op in releve["operations"]:
        if op.get("type_operation") == "FOURNISSEUR":
            retrouvee = "OUI" if op["facture"] else "NON"
        else:
            retrouvee = ""
        lignes.append({
            "Date": _format_date(op.get("date")),
            "Débit": op.get("debit"),
            "Crédit": op.get("credit"),
            "Libellé": op.get("libelle"),
            "Type d'opération": op.get("type_operation"),
            "Facture retrouvée": retrouvee,
        })
    return pd.DataFrame(lignes)


def tableau_dashboard(releve):
    """Reprend le relevé, uniquement les lignes fournisseurs, et y ajoute
    les colonnes de la facture rapprochée."""
    lignes = []
    for op in releve["operations"]:
        if op.get("type_operation") != "FOURNISSEUR":
            continue
        f = op["facture"] or {}
        lignes.append({
            "Date": _format_date(op.get("date")),
            "Montant en banque": -(op.get("debit") or 0),
            "Libellé": op.get("libelle"),
            "Facture retrouvée": "OUI" if f else "FACTURE MANQUANTE",
            "Date facture": _format_date(f.get("date")) if f else "",
            "TTC": -f["montant_ttc"] if f else None,
            "HT": -f["montant_ht"] if f.get("montant_ht") is not None else None,
            "TVA": -f["tva"] if f.get("tva") is not None else None,
            "Fournisseur": f.get("fournisseur", ""),
            "Fichier": f.get("fichier", ""),
            "Compte comptable": COMPTES.get(f.get("type_depense"), COMPTE_ATTENTE) if f else "",
        })
    return pd.DataFrame(lignes)


def en_csv(df):
    """CSV lisible directement par Excel français : point-virgule,
    virgule décimale, encodage avec BOM pour les accents."""
    return df.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")
