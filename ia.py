"""Lecture des factures et des relevés par l'IA Claude (Sonnet 5.5).

Les PDF sont envoyés tels quels à Claude, qui les lit comme une personne : texte,
colonnes, tableaux, et même scans. Rien n'est lu en local.

Utilisé seulement quand une clé ANTHROPIC_API_KEY est configurée.
Sans clé, l'app reste en mode démo et ce fichier n'est jamais appelé.
"""

import base64
import json

MODELE = "claude-sonnet-5-5"
# Effort de réflexion de Claude : bas pour une facture, moyen pour un relevé,
# qui compte beaucoup de lignes à recopier et à vérifier.
EFFORT_FACTURE = "low"
EFFORT_RELEVE = "medium"
TAILLE_MAX_PDF = 30 * 1024 * 1024  # l'API refuse une requête de plus de 32 Mo

TYPES_DEPENSE = ["Essence", "Fournitures bureau", "Matériel informatique",
                 "Déplacement", "Restaurant", "Marchandises", "Autre"]
TYPES_OPERATION = ["FOURNISSEUR", "CLIENT", "CARTE", "LCR", "REMISE", "AUTRE"]
TYPES_OPERATION_CARTE = ["FOURNISSEUR", "AUTRE"]


def _nul_ou(type_json):
    """Une valeur du type donné, ou null quand elle est absente ou illisible."""
    return {"anyOf": [{"type": type_json}, {"type": "null"}]}


# Forme exacte de la réponse de Claude : la sortie est toujours un JSON valide.
SCHEMA_FACTURE = {
    "type": "object",
    "properties": {
        "erreur": _nul_ou("string"),
        "date": _nul_ou("string"),
        "fournisseur": _nul_ou("string"),
        "montant_ttc": _nul_ou("number"),
        "montant_ht": _nul_ou("number"),
        "tva": _nul_ou("number"),
        "type_depense": {"type": "string", "enum": TYPES_DEPENSE},
    },
    "required": ["erreur", "date", "fournisseur", "montant_ttc", "montant_ht", "tva",
                 "type_depense"],
    "additionalProperties": False,
}

SCHEMA_VENTE = {
    "type": "object",
    "properties": {
        "erreur": _nul_ou("string"),
        "date": _nul_ou("string"),
        "client": _nul_ou("string"),
        "numero_facture": _nul_ou("string"),
        "montant_ttc": _nul_ou("number"),
        "montant_ht": _nul_ou("number"),
        "tva": _nul_ou("number"),
    },
    "required": ["erreur", "date", "client", "numero_facture", "montant_ttc", "montant_ht",
                 "tva"],
    "additionalProperties": False,
}

SCHEMA_RELEVE = {
    "type": "object",
    "properties": {
        "erreur": _nul_ou("string"),
        "banque": _nul_ou("string"),
        "solde_debut": _nul_ou("number"),
        "solde_fin": _nul_ou("number"),
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": _nul_ou("string"),
                    "libelle": {"type": "string"},
                    "debit": _nul_ou("number"),
                    "credit": _nul_ou("number"),
                    "type_operation": {"type": "string", "enum": TYPES_OPERATION},
                },
                "required": ["date", "libelle", "debit", "credit", "type_operation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["erreur", "banque", "solde_debut", "solde_fin", "operations"],
    "additionalProperties": False,
}

SCHEMA_CARTE = {
    "type": "object",
    "properties": {
        "erreur": _nul_ou("string"),
        "date_arrete": _nul_ou("string"),
        "date_prelevement": _nul_ou("string"),
        "total_net": _nul_ou("number"),
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": _nul_ou("string"),
                    "libelle": {"type": "string"},
                    "debit": _nul_ou("number"),
                    "credit": _nul_ou("number"),
                    "type_operation": {"type": "string", "enum": TYPES_OPERATION_CARTE},
                },
                "required": ["date", "libelle", "debit", "credit", "type_operation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["erreur", "date_arrete", "date_prelevement", "total_net", "operations"],
    "additionalProperties": False,
}

SCHEMA_LCR = {
    "type": "object",
    "properties": {
        "erreur": _nul_ou("string"),
        "numero": _nul_ou("string"),
        "date_reglement": _nul_ou("string"),
        "total": _nul_ou("number"),
        "total_refuse": _nul_ou("number"),
        "effets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tireur": {"type": "string"},
                    "reference": _nul_ou("string"),
                    "type_effet": _nul_ou("string"),
                    "echeance": _nul_ou("string"),
                    "numero_effet": _nul_ou("string"),
                    "montant": _nul_ou("number"),
                    "montant_refuse": _nul_ou("number"),
                },
                "required": ["tireur", "reference", "type_effet", "echeance", "numero_effet",
                             "montant", "montant_refuse"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["erreur", "numero", "date_reglement", "total", "total_refuse", "effets"],
    "additionalProperties": False,
}

SCHEMA_REMISE = {
    "type": "object",
    "properties": {
        "erreur": _nul_ou("string"),
        "numero": _nul_ou("string"),
        "date": _nul_ou("string"),
        "total": _nul_ou("number"),
        "cheques": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "emetteur": {"type": "string"},
                    "banque": _nul_ou("string"),
                    "montant": _nul_ou("number"),
                },
                "required": ["emetteur", "banque", "montant"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["erreur", "numero", "date", "total", "cheques"],
    "additionalProperties": False,
}

CONSIGNES_FACTURE = f"""Tu es l'assistant de BELGALANE, une application qui aide les dirigeants de TPE
à classer leurs factures d'achat. Tu reçois une facture fournisseur au format PDF.
Remplis les champs demandés :
- "date" : date de la facture au format AAAA-MM-JJ
- "fournisseur" : nom du fournisseur en majuscules
- "montant_ttc", "montant_ht", "tva" : nombres avec un point décimal, sans symbole €
- "type_depense" : une valeur parmi {TYPES_DEPENSE}
Règles strictes :
- N'invente jamais une valeur absente ou illisible : mets null.
- Ne calcule pas une valeur qui n'est pas écrite sur la facture.
- Le TTC est le total à payer, toutes taxes comprises (HT + TVA = TTC).
- Si le document n'est pas une facture, mets "erreur" à "pas une facture" et le reste à null."""

CONSIGNES_VENTE = """Tu es l'assistant de BELGALANE, une application qui aide les dirigeants de TPE
à suivre leurs ventes. Tu reçois une facture de vente au format PDF : une facture émise
par l'entreprise de l'utilisateur à l'un de ses clients.
Remplis les champs demandés :
- "date" : date de la facture au format AAAA-MM-JJ
- "client" : nom du client, c'est-à-dire le destinataire de la facture et non son émetteur,
  en majuscules
- "numero_facture" : numéro de la facture, tel qu'il est écrit
- "montant_ttc", "montant_ht", "tva" : nombres avec un point décimal, sans symbole €
Règles strictes :
- N'invente jamais une valeur absente ou illisible : mets null.
- Ne calcule pas une valeur qui n'est pas écrite sur la facture.
- Le TTC est le total à payer, toutes taxes comprises (HT + TVA = TTC).
- Si le document n'est pas une facture, mets "erreur" à "pas une facture" et le reste à null."""

CONSIGNES_RELEVE = f"""Tu es l'assistant de BELGALANE. Tu reçois un relevé de compte bancaire au format PDF.
Remplis les champs demandés :
- "banque" : nom de la banque
- "solde_debut", "solde_fin" : le solde précédent et le nouveau solde imprimés sur le relevé
  (négatifs si le solde est débiteur)
- "operations" : liste d'objets, un par opération, dans l'ordre du relevé, avec :
  "date" (AAAA-MM-JJ), "libelle" (court, avec le nom de la contrepartie : par exemple
  « PRLV BOUYGUES TELECOM »), "debit" (nombre ou null), "credit" (nombre ou null),
  "type_operation" (une valeur parmi {TYPES_OPERATION} : FOURNISSEUR pour un achat
  payé à une entreprise, CLIENT pour un encaissement client, CARTE pour le « DEBIT
  MENSUEL CARTE », c'est-à-dire le total des paiements par carte du mois, prélevé en
  une seule fois, LCR pour un « RELEVE LCR », c'est-à-dire le total des lettres de
  change (LCR) payées à des fournisseurs, détaillé sur un relevé de LCR à part,
  REMISE pour une « REMISE CHEQUE », c'est-à-dire des chèques de clients déposés en une
  seule fois, détaillés sur un bordereau de remise à part, AUTRE pour le reste : salaires,
  URSSAF, impôts, frais bancaires, apports, virements internes)
Les montants sont des nombres avec un point décimal, sans séparateur de milliers ni
symbole € (par exemple 1170.00 pour « 1.170,00 »).
Le sens d'une opération est donné par sa colonne : Débit (l'argent sort du compte)
ou Crédit (l'argent entre).
Règles strictes :
- N'invente jamais une valeur absente ou illisible : mets null.
- Recopie toutes les opérations de toutes les pages, sans en oublier ni en ajouter.
- Les lignes de solde (« SOLDE PRÉCÉDENT », « NOUVEAU SOLDE »), de report et de totaux
  ne sont pas des opérations.
- Vérifie ton travail : solde_debut + total des crédits - total des débits doit donner
  solde_fin, et si le relevé imprime les totaux des mouvements, ils doivent correspondre
  à la somme de tes débits et de tes crédits. S'il y a un écart, relis le relevé pour
  retrouver l'opération oubliée ou mal lue.
- Si le document n'est pas un relevé bancaire, mets "erreur" à "pas un relevé", le reste
  à null et "operations" à une liste vide."""

CONSIGNES_CARTE = f"""Tu es l'assistant de BELGALANE. Tu reçois un relevé de carte bancaire au format PDF :
le détail des paiements par carte d'un mois, prélevés en une seule fois sur le compte.
Remplis les champs demandés :
- "date_arrete" : date d'arrêté du relevé (AAAA-MM-JJ)
- "date_prelevement" : date de prélèvement sur le compte (AAAA-MM-JJ)
- "total_net" : le « total net des opérations » imprimé en bas du relevé, c'est-à-dire le
  montant prélevé sur le compte, sans signe
- "operations" : liste d'objets, un par opération, dans l'ordre du relevé, avec :
  "date" (AAAA-MM-JJ : sur le relevé l'année n'a que deux chiffres, 25 veut dire 2025),
  "libelle" (le nom du commerçant tel qu'il est écrit, par exemple « EXAPRINT.FR 34
  MONTPELLIER », sans la mention « COMMERCE ELECTRONIQUE »), "debit" (nombre ou null),
  "credit" (nombre ou null), "type_operation" (une valeur parmi {TYPES_OPERATION_CARTE} :
  FOURNISSEUR pour un achat chez un commerçant ou un fournisseur, y compris sur internet,
  AUTRE pour un retrait d'espèces, des frais ou un remboursement)
Les montants sont des nombres avec un point décimal, sans séparateur de milliers ni
symbole € (par exemple 3044.48 pour « 3 044,48 »).
Le sens d'une opération est donné par sa colonne : Débit (l'argent sort du compte)
ou Crédit (l'argent entre).
Règles strictes :
- N'invente jamais une valeur absente ou illisible : mets null.
- Recopie toutes les opérations de toutes les pages, y compris celles faites hors de
  France, sans en oublier ni en ajouter.
- Les lignes de total ne sont pas des opérations.
- Vérifie ton travail : total des débits - total des crédits doit donner total_net. S'il y
  a un écart, relis le relevé pour retrouver l'opération oubliée ou mal lue.
- Si le document n'est pas un relevé de carte, mets "erreur" à "pas un relevé de carte",
  le reste à null et "operations" à une liste vide."""

CONSIGNES_LCR = """Tu es l'assistant de BELGALANE. Tu reçois un « relevé de LCR/BOR » au format PDF :
le détail des lettres de change (LCR) de fournisseurs, payées en une seule fois par la banque.
Remplis les champs demandés :
- "numero" : le numéro du relevé, tel qu'il est écrit (par exemple 08185486), zéros du début
  compris
- "date_reglement" : la date de règlement (AAAA-MM-JJ)
- "total" : le total du relevé ; "total_refuse" : le total refusé
- "effets" : liste d'objets, un par ligne du tableau, dans l'ordre du relevé, avec :
  "tireur" (le nom du tireur, c'est-à-dire du fournisseur, en majuscules), "reference"
  (colonne Référence, ou null si elle est vide), "type_effet" (NA, A ou B, ou null),
  "echeance" (AAAA-MM-JJ), "numero_effet" (colonne numéro, zéros du début compris),
  "montant" et "montant_refuse" (nombres)
Les montants sont des nombres avec un point décimal, sans séparateur de milliers ni
symbole € (par exemple 1776.69 pour « 1 776,69 »).
Règles strictes :
- N'invente jamais une valeur absente ou illisible : mets null.
- Recopie toutes les lignes du tableau, sans en oublier ni en ajouter.
- Vérifie ton travail : la somme des montants des effets doit donner "total". S'il y a un
  écart, relis le relevé pour retrouver la ligne oubliée ou mal lue.
- Si le document n'est pas un relevé de LCR, mets "erreur" à "pas un relevé de LCR", le
  reste à null et "effets" à une liste vide."""

CONSIGNES_REMISE = """Tu es l'assistant de BELGALANE. Tu reçois un bordereau de remise de chèques au
format PDF : le détail des chèques de clients déposés à la banque en une seule fois. C'est
souvent un scan, parfois tourné, avec des parties écrites à la main : lis-le comme une
personne. L'image d'un chèque peut figurer sur la page : elle sert seulement à vérifier le
montant.
Remplis les champs demandés :
- "numero" : le numéro du bordereau (« Bordereau N° »), tel qu'il est écrit, zéros du début
  compris (par exemple 0000519)
- "date" : la date de la remise (AAAA-MM-JJ)
- "total" : le montant total de la remise (nombre)
- "cheques" : liste d'objets, un par chèque inscrit sur le bordereau, avec : "emetteur"
  (le nom de l'émetteur du chèque, tel qu'il est écrit), "banque" (la banque de l'émetteur,
  ou null) et "montant" (nombre)
Les montants sont des nombres avec un point décimal, sans séparateur de milliers ni
symbole € (par exemple 234.00 pour « 234,00 »).
Règles strictes :
- N'invente jamais une valeur absente ou illisible : mets null.
- Ne recopie que les chèques réellement inscrits sur le bordereau.
- Vérifie ton travail : la somme des montants des chèques doit donner "total". S'il y a un
  écart, relis le bordereau.
- Si le document n'est pas un bordereau de remise de chèques, mets "erreur" à "pas une
  remise de chèques", le reste à null et "cheques" à une liste vide."""


def _lire_pdf(fichier):
    """Contenu du PDF en base64, comme l'API le demande."""
    octets = fichier.getvalue() if hasattr(fichier, "getvalue") else fichier.read()
    if not octets:
        raise ValueError("le fichier est vide.")
    if len(octets) > TAILLE_MAX_PDF:
        raise ValueError("ce PDF dépasse 30 Mo : Claude ne peut pas le lire.")
    return base64.standard_b64encode(octets).decode("ascii")


def appeler_claude(cle, fichier, consignes, schema, effort, max_tokens):
    """Envoie le PDF à Claude et renvoie sa réponse JSON, sous forme de dict."""
    import anthropic  # importé ici : le mode démo n'a pas besoin du paquet

    pdf = _lire_pdf(fichier)
    client = anthropic.Anthropic(api_key=cle)
    try:
        with client.messages.stream(
            model=MODELE,
            max_tokens=max_tokens,
            system=consignes,
            output_config={"effort": effort,
                           "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": pdf}},
                {"type": "text", "text": "Voici le document à analyser."},
            ]}],
        ) as flux:
            reponse = flux.get_final_message()
    except anthropic.AuthenticationError as e:
        raise ValueError("clé Anthropic refusée : vérifiez ANTHROPIC_API_KEY.") from e
    except anthropic.RateLimitError as e:
        raise ValueError("trop de demandes envoyées à Claude : réessayez dans une minute.") from e
    except anthropic.APIConnectionError as e:
        raise ValueError("impossible de joindre Claude : vérifiez la connexion internet.") from e
    except anthropic.APIStatusError as e:
        if e.status_code == 402:
            raise ValueError("crédit Anthropic épuisé : vérifiez la facturation du compte.") from e
        raise ValueError(f"Claude a répondu par une erreur ({e.status_code}) : {e.message}") from e
    if reponse.stop_reason == "refusal":
        raise ValueError("Claude a refusé de traiter ce document.")
    if reponse.stop_reason == "max_tokens":
        raise ValueError("le document est trop long pour être lu en une fois.")
    # Une réponse peut commencer par un bloc de réflexion : on lit le bloc de texte.
    texte = next((b.text for b in reponse.content if b.type == "text"), "")
    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as e:
        raise ValueError("la réponse de Claude est illisible, réessayez.") from e
    if donnees.get("erreur"):
        raise ValueError(donnees["erreur"])
    return donnees


def _nombre(valeur):
    """Arrondit un montant au centime, ou None s'il n'est pas lu."""
    return None if valeur is None else round(float(valeur), 2)


def _montants(d):
    """Renvoie (TTC, HT, TVA) lus par Claude."""
    montant_ttc = _nombre(d.get("montant_ttc"))
    montant_ht = _nombre(d.get("montant_ht"))
    # Contrôle de cohérence : le HT ne peut jamais dépasser le TTC.
    # Si c'est le cas, l'IA s'est trompée : on préfère laisser le HT vide.
    if montant_ht is not None and montant_ttc is not None and montant_ht > montant_ttc:
        montant_ht = None
    return montant_ttc, montant_ht, _nombre(d.get("tva"))


def extraire_facture(cle, fichier):
    d = appeler_claude(cle, fichier, CONSIGNES_FACTURE, SCHEMA_FACTURE, EFFORT_FACTURE, 16000)
    type_depense = d.get("type_depense")
    montant_ttc, montant_ht, tva = _montants(d)
    return {
        "date": d.get("date"),
        "fournisseur": (d.get("fournisseur") or "INCONNU").upper(),
        "montant_ttc": montant_ttc,
        "montant_ht": montant_ht,
        "tva": tva,
        "type_depense": type_depense if type_depense in TYPES_DEPENSE else "Autre",
        "fichier": fichier.name,
    }


def extraire_vente(cle, fichier):
    d = appeler_claude(cle, fichier, CONSIGNES_VENTE, SCHEMA_VENTE, EFFORT_FACTURE, 16000)
    montant_ttc, montant_ht, tva = _montants(d)
    return {
        "date": d.get("date"),
        "client": (d.get("client") or "INCONNU").upper(),
        "montant_ttc": montant_ttc,
        "montant_ht": montant_ht,
        "tva": tva,
        "numero_facture": d.get("numero_facture") or "",
        "fichier": fichier.name,
    }


def _operations(d, types):
    """Les opérations lues par Claude, avec un type d'opération toujours valide."""
    operations = []
    for op in d.get("operations") or []:
        type_op = (op.get("type_operation") or "").upper()
        operations.append({
            "date": op.get("date"),
            "libelle": op.get("libelle") or "",
            "debit": _nombre(op.get("debit")),
            "credit": _nombre(op.get("credit")),
            "type_operation": type_op if type_op in types else "AUTRE",
        })
    return operations


def extraire_releve(cle, fichier):
    d = appeler_claude(cle, fichier, CONSIGNES_RELEVE, SCHEMA_RELEVE, EFFORT_RELEVE, 64000)
    return {
        "banque": d.get("banque") or "",
        "fichier": fichier.name,
        "solde_debut": _nombre(d.get("solde_debut")) or 0.0,
        "solde_fin": _nombre(d.get("solde_fin")) or 0.0,
        "operations": _operations(d, TYPES_OPERATION),
    }


def extraire_lcr(cle, fichier):
    d = appeler_claude(cle, fichier, CONSIGNES_LCR, SCHEMA_LCR, EFFORT_RELEVE, 32000)
    total = _nombre(d.get("total"))
    if total is None:
        raise ValueError("le total du relevé de LCR n'a pas pu être lu, réessayez.")
    # Chaque effet est rangé comme une opération du compte : date d'échéance, tireur
    # (le fournisseur) en libellé, montant au débit, plus les détails propres aux LCR.
    effets = [{
        "date": e.get("echeance"),
        "libelle": (e.get("tireur") or "").strip(),
        "debit": _nombre(e.get("montant")),
        "credit": None,
        "type_operation": "FOURNISSEUR",
        "reference": e.get("reference"),
        "type_effet": e.get("type_effet"),
        "numero_effet": e.get("numero_effet"),
        "montant_refuse": _nombre(e.get("montant_refuse")) or 0.0,
    } for e in d.get("effets") or []]
    return {
        "fichier": fichier.name,
        "numero": d.get("numero"),
        "date_reglement": d.get("date_reglement"),
        "total": total,
        "total_refuse": _nombre(d.get("total_refuse")) or 0.0,
        "operations": effets,
    }


def extraire_remise(cle, fichier):
    d = appeler_claude(cle, fichier, CONSIGNES_REMISE, SCHEMA_REMISE, EFFORT_RELEVE, 16000)
    total = _nombre(d.get("total"))
    if total is None:
        raise ValueError("le montant total de la remise de chèques n'a pas pu être lu, "
                         "réessayez.")
    # Chaque chèque est rangé comme une opération du compte : date de la remise, émetteur
    # en libellé, montant au crédit.
    cheques = [{
        "date": d.get("date"),
        "libelle": (c.get("emetteur") or "").strip(),
        "debit": None,
        "credit": _nombre(c.get("montant")),
        "type_operation": "CLIENT",
        "banque": c.get("banque"),
    } for c in d.get("cheques") or []]
    return {
        "fichier": fichier.name,
        "numero": d.get("numero"),
        "date": d.get("date"),
        "total": total,
        "operations": cheques,
    }


def extraire_carte(cle, fichier):
    d = appeler_claude(cle, fichier, CONSIGNES_CARTE, SCHEMA_CARTE, EFFORT_RELEVE, 64000)
    total_net = _nombre(d.get("total_net"))
    if total_net is None:
        raise ValueError("le total du relevé de carte n'a pas pu être lu, réessayez.")
    return {
        "fichier": fichier.name,
        "date_arrete": d.get("date_arrete"),
        "date_prelevement": d.get("date_prelevement"),
        "total_net": total_net,
        "operations": _operations(d, TYPES_OPERATION_CARTE),
    }
