"""Lecture des PDF et extraction par l'IA Mistral (Ministral 8B).

Utilisé seulement quand une clé MISTRAL_API_KEY est configurée.
Sans clé, l'app reste en mode démo et ce fichier n'est jamais appelé.
"""

import json

import requests
from pypdf import PdfReader

URL_MISTRAL = "https://api.mistral.ai/v1/chat/completions"
MODELE = "ministral-8b-latest"
LONGUEUR_MAX = 20000  # caractères envoyés à l'IA, pour limiter la consommation

TYPES_DEPENSE = ["Essence", "Fournitures bureau", "Matériel informatique",
                 "Déplacement", "Restaurant", "Marchandises", "Autre"]
TYPES_OPERATION = ["FOURNISSEUR", "CLIENT", "AUTRE"]

CONSIGNES_FACTURE = f"""Tu es l'assistant de BELGALANE, une application qui aide les dirigeants de TPE
à classer leurs factures d'achat. Tu reçois le texte d'une facture fournisseur.
Réponds UNIQUEMENT avec un objet JSON, sans aucun texte autour, avec exactement ces champs :
- "date" : date de la facture au format AAAA-MM-JJ
- "fournisseur" : nom du fournisseur en majuscules
- "montant_ttc", "montant_ht", "tva" : nombres avec un point décimal, sans symbole €
- "type_depense" : une valeur parmi {TYPES_DEPENSE}
Règles strictes :
- N'invente jamais une valeur absente ou illisible : mets null.
- Ne calcule pas une valeur qui n'est pas écrite sur la facture.
- Si le texte n'est pas une facture, réponds {{"erreur": "pas une facture"}}."""

CONSIGNES_RELEVE = f"""Tu es l'assistant de BELGALANE. Tu reçois le texte d'un relevé de compte bancaire.
Réponds UNIQUEMENT avec un objet JSON, sans aucun texte autour, avec exactement ces champs :
- "banque" : nom de la banque
- "solde_debut", "solde_fin" : nombres (négatifs si le solde est débiteur)
- "operations" : liste d'objets, un par ligne du relevé, avec :
  "date" (AAAA-MM-JJ), "libelle", "debit" (nombre ou null), "credit" (nombre ou null),
  "type_operation" (une valeur parmi {TYPES_OPERATION} : FOURNISSEUR pour un achat
  payé à une entreprise, CLIENT pour un encaissement client, AUTRE pour le reste :
  salaires, URSSAF, impôts, frais bancaires, apports, virements internes)
Règles strictes :
- N'invente jamais une valeur absente ou illisible : mets null.
- Recopie toutes les opérations, sans en oublier ni en ajouter.
- Si le texte n'est pas un relevé bancaire, réponds {{"erreur": "pas un relevé"}}."""


def lire_texte_pdf(fichier):
    """Extrait le texte d'un PDF généré par logiciel (pas d'OCR)."""
    lecteur = PdfReader(fichier)
    texte = "\n".join(page.extract_text() or "" for page in lecteur.pages).strip()
    if not texte:
        raise ValueError("aucun texte trouvé : ce PDF est probablement un scan "
                         "ou une photo, non pris en charge pour l'instant.")
    return texte[:LONGUEUR_MAX]


def appeler_mistral(cle, consignes, texte):
    reponse = requests.post(
        URL_MISTRAL,
        headers={"Authorization": f"Bearer {cle}"},
        json={
            "model": MODELE,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": consignes},
                {"role": "user", "content": texte},
            ],
        },
        timeout=60,
    )
    reponse.raise_for_status()
    contenu = reponse.json()["choices"][0]["message"]["content"]
    donnees = json.loads(contenu)
    if "erreur" in donnees:
        raise ValueError(donnees["erreur"])
    return donnees


def _nombre(valeur):
    """Convertit en nombre, ou None si ce n'est pas lisible."""
    if valeur is None:
        return None
    try:
        return round(float(str(valeur).replace(" ", "").replace(",", ".")), 2)
    except ValueError:
        return None


def extraire_facture(cle, fichier):
    d = appeler_mistral(cle, CONSIGNES_FACTURE, lire_texte_pdf(fichier))
    type_depense = d.get("type_depense")
    montant_ttc = _nombre(d.get("montant_ttc"))
    montant_ht = _nombre(d.get("montant_ht"))
    # Contrôle de cohérence : le HT ne peut jamais dépasser le TTC.
    # Si c'est le cas, l'IA s'est trompée : on préfère laisser le HT vide.
    if montant_ht is not None and montant_ttc is not None and montant_ht > montant_ttc:
        montant_ht = None
    return {
        "date": d.get("date"),
        "fournisseur": (d.get("fournisseur") or "INCONNU").upper(),
        "montant_ttc": montant_ttc,
        "montant_ht": montant_ht,
        "tva": _nombre(d.get("tva")),
        "type_depense": type_depense if type_depense in TYPES_DEPENSE else "Autre",
        "fichier": fichier.name,
    }


def extraire_releve(cle, fichier):
    d = appeler_mistral(cle, CONSIGNES_RELEVE, lire_texte_pdf(fichier))
    operations = []
    for op in d.get("operations") or []:
        type_op = (op.get("type_operation") or "").upper()
        operations.append({
            "date": op.get("date"),
            "libelle": op.get("libelle") or "",
            "debit": _nombre(op.get("debit")),
            "credit": _nombre(op.get("credit")),
            "type_operation": type_op if type_op in TYPES_OPERATION else "AUTRE",
        })
    return {
        "banque": d.get("banque") or "",
        "fichier": fichier.name,
        "solde_debut": _nombre(d.get("solde_debut")) or 0.0,
        "solde_fin": _nombre(d.get("solde_fin")) or 0.0,
        "operations": operations,
    }
    
