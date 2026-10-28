"""Logique de BELGALANE : doublons, rapprochement, contrôle de solde, tableaux.

Tout ici est du calcul exact fait par Python. L'IA n'intervient pas :
elle se contente de lire les PDF (voir ia.py).
"""

import re
import unicodedata
from datetime import date

import pandas as pd

# Écart maximal, en jours, entre la date d'une facture et son paiement.
TOLERANCE_JOURS = 15
# Même écart pour les paiements différés (effets de LCR, chèques remis) : la facture peut
# dater de plusieurs semaines avant l'échéance ou la remise.
TOLERANCE_DIFFEREE_JOURS = 90
# Écart maximal, en jours, entre la date d'un justificatif (relevé de carte, de LCR,
# bordereau de remise) et celle de sa ligne sur le relevé de banque.
TOLERANCE_PRELEVEMENT_JOURS = 5

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
# Compte proposé pour une vente (706000 : prestations de services).
COMPTE_VENTE = "706000"


def _en_date(texte):
    try:
        return date.fromisoformat(texte)
    except (TypeError, ValueError):
        return None


def _format_date(texte):
    d = _en_date(texte)
    return d.strftime("%d/%m/%Y") if d else texte


def _mots(op):
    """Le libellé d'une opération en majuscules et sans accents, pour y chercher des mots."""
    libelle = unicodedata.normalize("NFD", op.get("libelle") or "").upper()
    return libelle.encode("ascii", "ignore").decode()


def est_debit_carte(op):
    """Vrai pour la ligne « débit mensuel carte » d'un relevé de banque : le total des
    paiements par carte du mois, détaillé sur un relevé de carte à part."""
    mots = _mots(op)
    return op.get("type_operation") == "CARTE" or ("MENSUEL" in mots and "CARTE" in mots)


def est_debit_lcr(op):
    """Vrai pour la ligne « relevé LCR » d'un relevé de banque : le total des effets
    payés à des fournisseurs, détaillé sur un relevé de LCR à part."""
    return op.get("type_operation") == "LCR" or re.search(r"\bLCR\b", _mots(op)) is not None


def est_remise_cheques(op):
    """Vrai pour la ligne « remise chèque » d'un relevé de banque : des chèques de clients
    déposés en une fois, détaillés sur un bordereau de remise à part."""
    mots = _mots(op)
    return (op.get("type_operation") == "REMISE"
            or ("REMISE" in mots and ("CHEQUE" in mots or "CHQ" in mots)))


def est_ligne_detaillee(op):
    """Vrai pour une ligne du relevé de banque qui regroupe plusieurs paiements : ce sont
    ses détails, et non la ligne elle-même, que l'on rapproche des factures."""
    return est_debit_carte(op) or est_debit_lcr(op) or est_remise_cheques(op)


def _cle_doublon(f, tiers):
    """Ce qui identifie une facture : son fournisseur (son client, pour une vente), sa
    date et son montant TTC, plus son numéro quand il est lu. Quand la date ou le montant
    n'a pas été lu, le nom du fichier s'y ajoute : deux factures illisibles ne sont pas
    pour autant les mêmes."""
    cle = ((f.get(tiers) or "").upper().strip(), f.get("date"), f.get("montant_ttc"))
    if f.get("date") is None or f.get("montant_ttc") is None:
        cle += (f.get("fichier"),)
    if f.get("numero_facture"):  # deux ventes de même jour et même montant, numéros différents
        cle += (f["numero_facture"],)
    return cle


def marquer_doublons(factures, tiers="fournisseur"):
    """Une facture est un doublon si une précédente a le même fournisseur
    (le même client, pour des ventes), la même date et le même montant TTC."""
    deja_vues = set()
    for f in factures:
        cle = _cle_doublon(f, tiers)
        f["doublon"] = cle in deja_vues
        deja_vues.add(cle)


def ajouter_facture(factures, nouvelle, tiers="fournisseur"):
    """Ajoute une facture à la liste, sauf si la même y est déjà (même clé que
    marquer_doublons). Renvoie False, sans rien ajouter, dans ce cas."""
    cle = _cle_doublon(nouvelle, tiers)
    if any(_cle_doublon(f, tiers) == cle for f in factures):
        return False
    factures.append(nouvelle)
    return True


def retirer_doublons(factures, tiers="fournisseur"):
    """Retire de la liste les factures déjà présentes plus haut, et renvoie combien."""
    vues, gardees = set(), []
    for f in factures:
        cle = _cle_doublon(f, tiers)
        if cle not in vues:
            vues.add(cle)
            gardees.append(f)
    retirees = len(factures) - len(gardees)
    factures[:] = gardees
    return retirees


def _rapprocher(factures, operations, type_operation, sens, lien, tolerance=TOLERANCE_JOURS):
    """Associe chaque opération du type donné (un débit ou un crédit, selon `sens`) à une
    facture de même montant TTC, à `tolerance` jours près, en prenant la date la plus
    proche. La facture trouvée est rangée dans op[lien]. Les lignes qui regroupent
    plusieurs paiements et les effets refusés n'y participent pas."""
    for op in operations:
        op[lien] = None

    for op in operations:
        if (op.get("type_operation") != type_operation or not op.get(sens)
                or est_ligne_detaillee(op) or (op.get("montant_refuse") or 0) > 0):
            continue
        date_op = _en_date(op.get("date"))
        meilleure, meilleur_ecart = None, None
        for f in factures:
            if f["doublon"] or f["retrouve"] or f.get("montant_ttc") is None:
                continue
            if abs(f["montant_ttc"] - op[sens]) > 0.01:
                continue
            date_f = _en_date(f.get("date"))
            ecart = abs((date_f - date_op).days) if date_f and date_op else tolerance
            if ecart > tolerance:
                continue
            if meilleure is None or ecart < meilleur_ecart:
                meilleure, meilleur_ecart = f, ecart
        if meilleure:
            meilleure["retrouve"] = True
            op[lien] = meilleure


def rapprocher(factures, operations, operations_differees=()):
    """Associe chaque débit fournisseur du relevé de banque et de la carte à une facture
    d'achat, puis chaque effet des relevés de LCR (`operations_differees`), avec une
    tolérance plus large."""
    for f in factures:
        f["retrouve"] = False
    _rapprocher(factures, operations, "FOURNISSEUR", "debit", "facture")
    _rapprocher(factures, operations_differees, "FOURNISSEUR", "debit", "facture",
                TOLERANCE_DIFFEREE_JOURS)


def rapprocher_ventes(ventes, operations, operations_differees=()):
    """Associe chaque encaissement client du relevé de banque à une facture de vente,
    puis chaque chèque des bordereaux de remise (`operations_differees`), avec une
    tolérance plus large."""
    for v in ventes:
        v["retrouve"] = False
    _rapprocher(ventes, operations, "CLIENT", "credit", "vente")
    _rapprocher(ventes, operations_differees, "CLIENT", "credit", "vente",
                TOLERANCE_DIFFEREE_JOURS)


def controle_solde(releve):
    """Renvoie (solde calculé, écart avec le solde de fin lu sur le relevé)."""
    credits = sum(op.get("credit") or 0 for op in releve["operations"])
    debits = sum(op.get("debit") or 0 for op in releve["operations"])
    calcule = round(releve["solde_debut"] + credits - debits, 2)
    return calcule, round(releve["solde_fin"] - calcule, 2)


def _periode(releve):
    """(première, dernière) date des opérations d'un relevé, ou (None, None) s'il n'a
    aucune opération datée."""
    dates = sorted(op["date"] for op in releve["operations"] if _en_date(op.get("date")))
    return (dates[0], dates[-1]) if dates else (None, None)


def libelle_releve(releve):
    """Nom lisible d'un relevé : son fichier et sa période."""
    debut, fin = _periode(releve)
    if not debut:
        return f"« {releve['fichier']} »"
    return f"« {releve['fichier']} » (du {_format_date(debut)} au {_format_date(fin)})"


def meme_releve(a, b):
    """Deux relevés sont les mêmes s'ils ont les mêmes soldes de début et de fin et la
    même période. Sans opération datée, on compare aussi le nom du fichier : deux mois
    sans mouvement peuvent avoir les mêmes soldes."""
    if (abs(a["solde_debut"] - b["solde_debut"]) >= 0.01
            or abs(a["solde_fin"] - b["solde_fin"]) >= 0.01
            or _periode(a) != _periode(b)):
        return False
    return _periode(a)[0] is not None or a["fichier"] == b["fichier"]


def ajouter_releve(releves, nouveau):
    """Ajoute un relevé à la liste, rangée par date, sans toucher aux relevés déjà là.
    Renvoie False, sans rien ajouter, si le relevé est déjà dans la liste."""
    if any(meme_releve(r, nouveau) for r in releves):
        return False
    releves.append(nouveau)
    # Les relevés sans date vont à la fin.
    releves.sort(key=lambda r: _periode(r) if _periode(r)[0] else ("9999-12-31", ""))
    return True


def releves_manquants(releves):
    """Renvoie un message court, (titre, détail), par trou entre deux relevés qui se
    suivent (liste rangée par date) : le solde de fin du premier doit être le solde de
    début du suivant."""
    messages = []
    for avant, apres in zip(releves, releves[1:]):
        if abs(avant["solde_fin"] - apres["solde_debut"]) < 0.01:
            continue
        fin_avant, debut_apres = _periode(avant)[1], _periode(apres)[0]
        if fin_avant and debut_apres and debut_apres <= fin_avant:
            messages.append(("Relevés qui se chevauchent",
                             f"vers le {_format_date(debut_apres)}"))
        elif fin_avant and debut_apres:
            messages.append(("Manque relevé intermédiaire",
                             f"entre le {_format_date(fin_avant)} et le {_format_date(debut_apres)}"))
        else:
            messages.append(("Manque relevé intermédiaire", ""))
    return messages


def fusionner_releves(releves):
    """Un seul relevé qui réunit tous les relevés (rangés par date) : soldes de début du
    premier et de fin du dernier, opérations mises bout à bout. None s'il n'y en a pas."""
    if not releves:
        return None
    return {
        "banque": releves[0]["banque"],
        "fichier": ", ".join(r["fichier"] for r in releves),
        "solde_debut": releves[0]["solde_debut"],
        "solde_fin": releves[-1]["solde_fin"],
        "operations": [op for r in releves for op in r["operations"]],
    }


def tableau_releves(releves):
    """Un tableau qui liste les relevés importés, avec leur contrôle de solde."""
    lignes = []
    for r in releves:
        debut, fin = _periode(r)
        _, ecart = controle_solde(r)
        lignes.append({
            "Fichier": r["fichier"],
            "Du": _format_date(debut) if debut else "",
            "Au": _format_date(fin) if fin else "",
            "Solde début": r["solde_debut"],
            "Solde fin": r["solde_fin"],
            "Contrôle du solde": "OUI" if abs(ecart) < 0.01 else "NON",
        })
    return pd.DataFrame(lignes)


# ---------- Justificatifs d'une ligne du relevé de banque ----------
# Trois sortes de documents détaillent une ligne qui regroupe plusieurs paiements :
#   - le relevé de carte        (ligne « débit mensuel carte », achats par carte) ;
#   - le relevé de LCR          (ligne « relevé LCR », effets payés à des fournisseurs) ;
#   - le bordereau de remise    (ligne « remise chèque », chèques de clients).
# Chacun est un dict avec son fichier, son total et ses « operations » (les paiements
# détaillés, sous la même forme que ceux du relevé de banque).

def _ajouter_detail(liste, nouveau, meme, cle_date):
    """Ajoute un justificatif à la liste, rangée par date, sauf si le même y est déjà.
    Renvoie False, sans rien ajouter, dans ce cas."""
    if any(meme(d, nouveau) for d in liste):
        return False
    liste.append(nouveau)
    liste.sort(key=lambda d: d.get(cle_date) or "9999-12-31")
    return True


def _meme_numero(a, b, cle_date):
    """Deux justificatifs numérotés sont les mêmes s'ils ont le même numéro ; sans numéro
    lu, s'ils ont le même total et la même date."""
    if a.get("numero") and b.get("numero"):
        return a["numero"] == b["numero"]
    return abs(a["total"] - b["total"]) < 0.01 and a.get(cle_date) == b.get(cle_date)


def _controle(detail, sens, total):
    """Renvoie (somme des paiements détaillés, écart avec le total lu)."""
    calcule = round(sum(op.get(sens) or 0 for op in detail["operations"]), 2)
    return calcule, round(total - calcule, 2)


def _lier_detail(operations, details, lien, est_ligne, sens, montant, cle_date):
    """Associe chaque justificatif à la ligne du relevé de banque qui lui correspond : une
    ligne du bon genre (`est_ligne`), du même montant (`montant(detail)`, au débit ou au
    crédit selon `sens`). Si le numéro du justificatif figure dans le libellé de la ligne,
    c'est elle ; sinon les dates doivent tomber à TOLERANCE_PRELEVEMENT_JOURS près.
    Le justificatif trouvé est rangé dans op[lien]."""
    for op in operations:
        op[lien] = None
    for detail in details:
        numero = detail.get("numero")
        date_detail = _en_date(detail.get(cle_date))
        meilleure, meilleur_ecart = None, None
        for op in operations:
            if op[lien] or not est_ligne(op):
                continue
            if abs((op.get(sens) or 0) - montant(detail)) > 0.01:
                continue
            if numero and numero in (op.get("libelle") or ""):
                ecart = -1
            else:
                date_op = _en_date(op.get("date"))
                ecart = (abs((date_op - date_detail).days) if date_op and date_detail
                         else TOLERANCE_PRELEVEMENT_JOURS)
                if ecart > TOLERANCE_PRELEVEMENT_JOURS:
                    continue
            if meilleure is None or ecart < meilleur_ecart:
                meilleure, meilleur_ecart = op, ecart
        if meilleure:
            meilleure[lien] = detail


def sans_ligne(operations, details, lien):
    """Les justificatifs qui ne correspondent à aucune ligne du relevé de banque."""
    return [d for d in details if not any(op.get(lien) is d for op in operations)]


# -- Relevé de carte : date d'arrêté, date de prélèvement, total net --
def meme_carte(a, b):
    """Deux relevés de carte sont les mêmes s'ils ont le même total et les mêmes dates."""
    return (abs(a["total_net"] - b["total_net"]) < 0.01
            and a.get("date_arrete") == b.get("date_arrete")
            and a.get("date_prelevement") == b.get("date_prelevement"))


def ajouter_carte(cartes, nouvelle):
    return _ajouter_detail(cartes, nouvelle, meme_carte, "date_prelevement")


def libelle_carte(carte):
    """Nom lisible d'un relevé de carte : son fichier et sa date de prélèvement."""
    prelevement = carte.get("date_prelevement")
    if not prelevement:
        return f"« {carte['fichier']} »"
    return f"« {carte['fichier']} » (prélevé le {_format_date(prelevement)})"


def controle_carte(carte):
    """Renvoie (total calculé, écart avec le total net lu sur le relevé de carte)."""
    credits = sum(op.get("credit") or 0 for op in carte["operations"])
    debits = sum(op.get("debit") or 0 for op in carte["operations"])
    calcule = round(debits - credits, 2)
    return calcule, round(carte["total_net"] - calcule, 2)


def rapprocher_cartes(operations, cartes):
    """Associe chaque relevé de carte à la ligne « débit mensuel carte » de même montant
    (rangé dans op["carte"])."""
    _lier_detail(operations, cartes, "carte", est_debit_carte, "debit",
                 lambda c: c["total_net"], "date_prelevement")


# -- Relevé de LCR : numéro, date de règlement, total, total refusé --
def meme_lcr(a, b):
    return _meme_numero(a, b, "date_reglement")


def ajouter_lcr(lcrs, nouveau):
    return _ajouter_detail(lcrs, nouveau, meme_lcr, "date_reglement")


def libelle_lcr(lcr):
    """Nom lisible d'un relevé de LCR : son fichier, son numéro et sa date de règlement."""
    details = ([f"n° {lcr['numero']}"] if lcr.get("numero") else [])
    if lcr.get("date_reglement"):
        details.append(f"réglé le {_format_date(lcr['date_reglement'])}")
    return f"« {lcr['fichier']} »" + (f" ({', '.join(details)})" if details else "")


def controle_lcr(lcr):
    """Renvoie (somme des effets, écart avec le total lu sur le relevé de LCR)."""
    return _controle(lcr, "debit", lcr["total"])


def rapprocher_lcr(operations, lcrs):
    """Associe chaque relevé de LCR à la ligne « relevé LCR » de même montant (le total
    moins les effets refusés), rangé dans op["lcr"]."""
    _lier_detail(operations, lcrs, "lcr", est_debit_lcr, "debit",
                 lambda lcr: round(lcr["total"] - (lcr.get("total_refuse") or 0), 2),
                 "date_reglement")


# -- Bordereau de remise de chèques : numéro, date, total --
def meme_remise(a, b):
    return _meme_numero(a, b, "date")


def ajouter_remise(remises, nouvelle):
    return _ajouter_detail(remises, nouvelle, meme_remise, "date")


def libelle_remise(remise):
    """Nom lisible d'une remise de chèques : son fichier, son numéro et sa date."""
    details = ([f"bordereau n° {remise['numero']}"] if remise.get("numero") else [])
    if remise.get("date"):
        details.append(f"du {_format_date(remise['date'])}")
    return f"« {remise['fichier']} »" + (f" ({', '.join(details)})" if details else "")


def controle_remise(remise):
    """Renvoie (somme des chèques, écart avec le total lu sur le bordereau)."""
    return _controle(remise, "credit", remise["total"])


def rapprocher_remises(operations, remises):
    """Associe chaque bordereau de remise à la ligne « remise chèque » de même montant,
    rangé dans op["remise"]."""
    _lier_detail(operations, remises, "remise", est_remise_cheques, "credit",
                 lambda r: r["total"], "date")


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


def tableau_ventes(ventes, releve_present):
    lignes = [{
        "Date": _format_date(v.get("date")),
        "Montant TTC": v.get("montant_ttc"),
        "Montant HT": v.get("montant_ht"),
        "TVA": v.get("tva"),
        "Client": v.get("client"),
        "Numéro facture": v.get("numero_facture") or "",
        "Retrouvé en banque": statut_facture(v, releve_present),
    } for v in ventes]
    return pd.DataFrame(lignes)


def tableau_banque(releve):
    lignes = []
    for op in releve["operations"]:
        type_op = op.get("type_operation")
        if est_ligne_detaillee(op):
            retrouvee = "OK" if (op.get("carte") or op.get("lcr") or op.get("remise")) else "NON"
        elif type_op == "FOURNISSEUR":
            retrouvee = "OUI" if op["facture"] else "NON"
        elif type_op == "CLIENT":
            retrouvee = "OUI" if op.get("vente") else "NON"
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


# Les colonnes sont fixées d'avance : sans ligne, le tableau garde ses colonnes.
COLONNES_DASHBOARD = ["Date", "Montant en banque", "Libellé", "Paiement",
                      "Facture retrouvée", "Date facture", "TTC", "HT", "TVA", "Fournisseur",
                      "Fichier", "Compte comptable"]
COLONNES_CARTE = ["Date", "Débit", "Crédit", "Libellé", "Type d'opération",
                  "Facture retrouvée", "Fichier facture"]
COLONNES_LCR = ["Échéance", "Montant", "Tireur", "Référence", "Type", "N° effet",
                "Montant refusé", "Facture retrouvée", "Fichier facture"]
COLONNES_REMISE = ["Date", "Montant", "Émetteur", "Banque", "Facture retrouvée", "Client",
                   "Numéro facture"]
COLONNES_DASHBOARD_VENTES = ["Date", "Montant en banque", "Libellé", "Paiement",
                             "Facture retrouvée", "Date facture", "TTC", "HT", "TVA", "Client",
                             "Numéro facture", "Compte comptable"]


def tableau_carte(carte):
    """Le détail d'un relevé de carte, avec la facture retrouvée pour chaque achat."""
    lignes = []
    for op in carte["operations"]:
        f = op.get("facture")
        if op.get("type_operation") != "FOURNISSEUR":
            retrouvee = ""
        else:
            retrouvee = "OUI" if f else "NON"
        lignes.append({
            "Date": _format_date(op.get("date")),
            "Débit": op.get("debit"),
            "Crédit": op.get("credit"),
            "Libellé": op.get("libelle"),
            "Type d'opération": op.get("type_operation"),
            "Facture retrouvée": retrouvee,
            "Fichier facture": f["fichier"] if f else "",
        })
    return pd.DataFrame(lignes, columns=COLONNES_CARTE)


def tableau_cartes(cartes, operations):
    """Un tableau qui liste les relevés de carte importés, avec leur contrôle de total
    et la ligne du relevé de banque qui leur correspond."""
    lignes = []
    for c in cartes:
        _, ecart = controle_carte(c)
        liee = any(op.get("carte") is c for op in operations)
        lignes.append({
            "Fichier": c["fichier"],
            "Arrêté le": _format_date(c.get("date_arrete")) or "",
            "Prélevé le": _format_date(c.get("date_prelevement")) or "",
            "Total net": c["total_net"],
            "Contrôle du total": "OUI" if abs(ecart) < 0.01 else "NON",
            "Ligne en banque": "OUI" if liee else "NON",
        })
    return pd.DataFrame(lignes)


def tableau_lcr(lcr):
    """Le détail d'un relevé de LCR, avec la facture retrouvée pour chaque effet."""
    lignes = []
    for op in lcr["operations"]:
        f = op.get("facture")
        if (op.get("montant_refuse") or 0) > 0:
            retrouvee = "REFUSÉ"
        else:
            retrouvee = "OUI" if f else "NON"
        lignes.append({
            "Échéance": _format_date(op.get("date")),
            "Montant": op.get("debit"),
            "Tireur": op.get("libelle"),
            "Référence": op.get("reference") or "",
            "Type": op.get("type_effet") or "",
            "N° effet": op.get("numero_effet") or "",
            "Montant refusé": op.get("montant_refuse"),
            "Facture retrouvée": retrouvee,
            "Fichier facture": f["fichier"] if f else "",
        })
    return pd.DataFrame(lignes, columns=COLONNES_LCR)


def tableau_remise(remise):
    """Le détail d'un bordereau de remise, avec la facture de vente retrouvée pour chaque
    chèque."""
    lignes = []
    for op in remise["operations"]:
        v = op.get("vente")
        lignes.append({
            "Date": _format_date(op.get("date")),
            "Montant": op.get("credit"),
            "Émetteur": op.get("libelle"),
            "Banque": op.get("banque") or "",
            "Facture retrouvée": "OUI" if v else "NON",
            "Client": v["client"] if v else "",
            "Numéro facture": (v.get("numero_facture") or "") if v else "",
        })
    return pd.DataFrame(lignes, columns=COLONNES_REMISE)


def tableau_lcrs(lcrs, operations):
    """Un tableau qui liste les relevés de LCR importés, avec leur contrôle de total et la
    ligne du relevé de banque qui leur correspond."""
    lignes = []
    for lcr in lcrs:
        _, ecart = controle_lcr(lcr)
        lignes.append({
            "Fichier": lcr["fichier"],
            "Numéro": lcr.get("numero") or "",
            "Réglé le": _format_date(lcr.get("date_reglement")) or "",
            "Total": lcr["total"],
            "Contrôle du total": "OUI" if abs(ecart) < 0.01 else "NON",
            "Ligne en banque": "OUI" if any(op.get("lcr") is lcr for op in operations) else "NON",
        })
    return pd.DataFrame(lignes)


def tableau_remises(remises, operations):
    """Un tableau qui liste les bordereaux de remise importés, avec leur contrôle de total
    et la ligne du relevé de banque qui leur correspond."""
    lignes = []
    for remise in remises:
        _, ecart = controle_remise(remise)
        lignes.append({
            "Fichier": remise["fichier"],
            "Bordereau": remise.get("numero") or "",
            "Date": _format_date(remise.get("date")) or "",
            "Total": remise["total"],
            "Contrôle du total": "OUI" if abs(ecart) < 0.01 else "NON",
            "Ligne en banque": ("OUI" if any(op.get("remise") is remise for op in operations)
                                else "NON"),
        })
    return pd.DataFrame(lignes)


def tableau_dashboard(releve, cartes=(), lcrs=()):
    """Reprend le relevé, uniquement les lignes fournisseurs, et y ajoute
    les colonnes de la facture rapprochée. Les achats détaillés sur les relevés de
    carte et les effets des relevés de LCR s'ajoutent aux autres lignes ; les lignes du
    relevé de banque qu'ils détaillent sont écartées, car leur détail les remplace."""
    sources = [(op, "Compte") for op in releve["operations"] if not est_ligne_detaillee(op)]
    sources += [(op, "Carte") for carte in cartes for op in carte["operations"]]
    sources += [(op, "LCR") for lcr in lcrs for op in lcr["operations"]
                if not op.get("montant_refuse")]
    sources.sort(key=lambda source: source[0].get("date") or "9999-12-31")
    lignes = []
    for op, paiement in sources:
        if op.get("type_operation") != "FOURNISSEUR":
            continue
        f = op["facture"] or {}
        lignes.append({
            "Date": _format_date(op.get("date")),
            "Montant en banque": -(op.get("debit") or 0),
            "Libellé": op.get("libelle"),
            "Paiement": paiement,
            "Facture retrouvée": "OUI" if f else "FACTURE MANQUANTE",
            "Date facture": _format_date(f.get("date")) if f else "",
            "TTC": -f["montant_ttc"] if f else None,
            "HT": -f["montant_ht"] if f.get("montant_ht") is not None else None,
            "TVA": -f["tva"] if f.get("tva") is not None else None,
            "Fournisseur": f.get("fournisseur", ""),
            "Fichier": f.get("fichier", ""),
            "Compte comptable": COMPTES.get(f.get("type_depense"), COMPTE_ATTENTE) if f else "",
        })
    return pd.DataFrame(lignes, columns=COLONNES_DASHBOARD)


def tableau_dashboard_ventes(releve, remises=()):
    """Comme tableau_dashboard, pour les encaissements clients du relevé et leur
    facture de vente, avec en plus les chèques des bordereaux de remise (la ligne
    « remise chèque » du relevé est écartée, son détail la remplace). Les montants
    restent positifs : ce sont des recettes."""
    sources = [(op, "Compte") for op in releve["operations"] if not est_ligne_detaillee(op)]
    sources += [(op, "Chèque") for remise in remises for op in remise["operations"]]
    sources.sort(key=lambda source: source[0].get("date") or "9999-12-31")
    lignes = []
    for op, paiement in sources:
        if op.get("type_operation") != "CLIENT" or not op.get("credit"):
            continue
        v = op.get("vente") or {}
        lignes.append({
            "Date": _format_date(op.get("date")),
            "Montant en banque": op["credit"],
            "Libellé": op.get("libelle"),
            "Paiement": paiement,
            "Facture retrouvée": "OUI" if v else "FACTURE MANQUANTE",
            "Date facture": _format_date(v.get("date")) if v else "",
            "TTC": v["montant_ttc"] if v else None,
            "HT": v.get("montant_ht"),
            "TVA": v.get("tva"),
            "Client": v.get("client", ""),
            "Numéro facture": v.get("numero_facture") or "",
            "Compte comptable": COMPTE_VENTE if v else "",
        })
    return pd.DataFrame(lignes, columns=COLONNES_DASHBOARD_VENTES)


def en_csv(df):
    """CSV lisible directement par Excel français : point-virgule,
    virgule décimale, encodage avec BOM pour les accents."""
    return df.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")
