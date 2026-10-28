"""BELGALANE : achats, ventes, banque et rapprochement, avec l'IA Claude.

Lancer en local : streamlit run app.py
"""

import copy
import html

import streamlit as st

import ia
import sample_data
import stockage
import traitement

st.set_page_config(page_title="BELGALANE", page_icon="📂", layout="wide")


def lire_secret(nom):
    """Lit un secret sans planter s'il n'existe pas."""
    try:
        return st.secrets.get(nom)
    except Exception:
        return None


# ---------- Mot de passe ----------
MOT_DE_PASSE = lire_secret("APP_PASSWORD")

if MOT_DE_PASSE and not st.session_state.get("connecte"):
    st.title("📂 BELGALANE")
    saisie = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter"):
        if saisie == MOT_DE_PASSE:
            st.session_state.connecte = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()

# ---------- Mode démo ou IA ----------
CLE_IA = lire_secret("ANTHROPIC_API_KEY")
MODE_DEMO = not CLE_IA

def sauver():
    """Enregistre les données dans la base (sauf en mode démo, où rien n'est conservé)."""
    if MODE_DEMO or not st.session_state.get("base_ok", True):
        return
    try:
        stockage.sauvegarder(st.session_state.factures, st.session_state.ventes,
                             st.session_state.releves, st.session_state.cartes,
                             st.session_state.lcrs, st.session_state.remises)
    except Exception as erreur:
        st.warning(f"Les données n'ont pas pu être enregistrées : {erreur}")


if "factures" not in st.session_state:
    if MODE_DEMO:
        st.session_state.factures = copy.deepcopy(sample_data.FACTURES_DEMO)
        st.session_state.ventes = copy.deepcopy(sample_data.VENTES_DEMO)
        st.session_state.releves = [copy.deepcopy(sample_data.RELEVE_BANCAIRE_DEMO)]
    else:
        # Reprend ce qui a été enregistré lors des sessions précédentes.
        try:
            (st.session_state.factures, st.session_state.ventes, st.session_state.releves,
             st.session_state.cartes, st.session_state.lcrs,
             st.session_state.remises) = stockage.charger()
        except Exception as erreur:
            # Base illisible : on repart de zéro sans l'écraser, pour ne rien détruire.
            st.session_state.factures, st.session_state.ventes = [], []
            st.session_state.releves = []
            st.session_state.base_ok = False
            st.error(f"La base de données n'a pas pu être lue ({erreur}) : "
                     "rien ne sera enregistré tant que ce n'est pas réglé.")

if "ventes" not in st.session_state:  # session ouverte avant l'ajout des ventes
    st.session_state.ventes = copy.deepcopy(sample_data.VENTES_DEMO) if MODE_DEMO else []

if "releves" not in st.session_state:  # session ouverte avant la liste de relevés
    ancien = st.session_state.get("releve")
    st.session_state.releves = [ancien] if ancien else []

# Relevés de carte, de LCR et bordereaux de remise : vides en mode démo, et dans une
# session ouverte avant leur ajout.
for liste in ("cartes", "lcrs", "remises"):
    if liste not in st.session_state:
        st.session_state[liste] = []

# Une session ouverte avant la sauvegarde enregistre une première fois ce qu'elle contient.
if not MODE_DEMO and not st.session_state.get("base_synchronisee"):
    sauver()
    st.session_state.base_synchronisee = True

factures = st.session_state.factures
ventes = st.session_state.ventes
releves = st.session_state.releves  # rangés par date, du plus ancien au plus récent
# Les pages travaillent sur un seul relevé qui réunit tous les relevés importés.
releve = traitement.fusionner_releves(releves)
trous_releves = traitement.releves_manquants(releves)
# Les justificatifs des lignes du relevé de banque qui regroupent plusieurs paiements,
# rangés par date : débits mensuels carte, relevés de LCR, remises de chèques.
cartes = st.session_state.cartes
lcrs = st.session_state.lcrs
remises = st.session_state.remises

# Une facture d'achat ou de vente déjà présente n'est jamais gardée en double (voir les
# imports plus bas) : on retire aussi les doublons enregistrés avant cette règle.
if traitement.retirer_doublons(factures) + traitement.retirer_doublons(ventes, "client"):
    sauver()

# Recalculé à chaque affichage : un relevé ajouté plus tard met
# automatiquement à jour la colonne « Retrouvé en banque ».
operations = releve["operations"] if releve else []
traitement.rapprocher_cartes(operations, cartes)
traitement.rapprocher_lcr(operations, lcrs)
traitement.rapprocher_remises(operations, remises)
# Un achat par carte se rapproche d'une facture comme un paiement du compte ; un effet de
# LCR ou un chèque remis, qui sont payés plus tard, avec une tolérance de date plus large.
operations_carte = [op for carte in cartes for op in carte["operations"]]
operations_lcr = [op for lcr in lcrs for op in lcr["operations"]]
operations_remise = [op for remise in remises for op in remise["operations"]]
traitement.marquer_doublons(factures)
traitement.rapprocher(factures, operations + operations_carte, operations_lcr)
traitement.marquer_doublons(ventes, "client")
traitement.rapprocher_ventes(ventes, operations, operations_remise)

# ---------- Affichage ----------
COULEURS = {
    "OUI": "background-color: rgba(46, 160, 67, 0.22)",
    "NON": "background-color: rgba(218, 54, 51, 0.22)",
    "FACTURE MANQUANTE": "background-color: rgba(218, 54, 51, 0.22)",
    "DOUBLON": "background-color: rgba(230, 150, 30, 0.25)",
    "REFUSÉ": "background-color: rgba(230, 150, 30, 0.25)",
}
# Texte du statut des lignes qui regroupent plusieurs paiements (débit mensuel carte,
# relevé LCR, remise chèque) : OK (justificatif importé) ou NON.
TEXTES_STATUT = {
    "OK": "color: rgb(46, 160, 67); font-weight: bold",
    "NON": "color: rgb(218, 54, 51); font-weight: bold",
}


def afficher_tableau(df, colonne_statut, cle_selection=None, lignes_en_gras=()):
    """Affiche le tableau, colorié selon la colonne de statut ; le statut des lignes
    `lignes_en_gras` (numéros) est en plus écrit en gras et en couleur. Avec une
    `cle_selection`, une ligne peut être cliquée : renvoie alors son numéro, ou None
    si aucune ne l'est."""
    def couleur_ligne(ligne):
        return [COULEURS.get(ligne[colonne_statut], "")] * len(ligne)

    def texte_statut(ligne):
        texte = TEXTES_STATUT.get(ligne[colonne_statut], "") if ligne.name in lignes_en_gras else ""
        return [texte if colonne == colonne_statut else "" for colonne in ligne.index]

    colonnes_nombres = df.select_dtypes("number").columns
    style = (df.style
             .apply(couleur_ligne, axis=1)
             .apply(texte_statut, axis=1)
             .format(precision=2, decimal=",", thousands=" ", na_rep="—",
                     subset=colonnes_nombres))
    if not cle_selection:
        st.dataframe(style, hide_index=True, width="stretch")
        return None
    evenement = st.dataframe(style, hide_index=True, width="stretch", key=cle_selection,
                             on_select="rerun", selection_mode="single-row")
    lignes = evenement.selection.rows
    return lignes[0] if lignes else None


def euros(montant):
    return f"{montant:,.2f} €".replace(",", " ").replace(".", ",")


def majuscule(texte):
    """Le texte avec sa première lettre en majuscule, le reste inchangé (LCR reste LCR)."""
    return texte[:1].upper() + texte[1:]


def afficher_alerte(titre, detail=""):
    """Encadré orange au texte court et lisible : un titre, et en plus petit un détail."""
    ligne_detail = (f'<div style="font-size: 0.85rem; margin-top: 0.2rem; opacity: 0.85;">'
                    f'{html.escape(detail)}</div>' if detail else "")
    st.markdown(
        '<div style="border: 2px solid rgb(230, 150, 30); border-radius: 0.6rem; '
        'background-color: rgba(230, 150, 30, 0.16); padding: 0.6rem 0.7rem; '
        'margin-bottom: 0.5rem; text-align: center;">'
        f'<div style="font-size: 1.1rem; font-weight: 700; line-height: 1.2;">'
        f'⚠️ {html.escape(titre)}</div>{ligne_detail}</div>',
        unsafe_allow_html=True)


def prevenir_doublons(noms, page):
    """Petite fenêtre qui s'efface seule : ces factures sont déjà dans la page donnée et
    n'ont pas été ajoutées. Rien n'est gardé sur les doublons."""
    debut = (f"Cette facture est déjà dans {page}, elle n'a pas été ajoutée"
             if len(noms) == 1 else
             f"{len(noms)} factures sont déjà dans {page}, elles n'ont pas été ajoutées")
    st.toast(f"{debut} : {', '.join(noms)}", icon="⚠️", duration="long")


# Les trois sortes de justificatifs d'une ligne du relevé de banque qui regroupe plusieurs
# paiements. Même principe pour chacune : on dépose ses PDF dans « Ajouter un relevé », on
# clique sur la ligne du relevé pour voir le détail, et chaque paiement détaillé est
# rapproché d'une facture.
JUSTIFICATIFS = [
    {"nom": "carte", "liste": "cartes", "lien": "carte", "sens": "debit",
     "singulier": "relevé de carte", "pluriel": "relevés de carte",
     "ligne": "débit mensuel carte", "elements": "achats",
     "legende": "Le détail d'une ligne « débit mensuel carte » du relevé de compte.",
     "titre_detail": "Détail du débit mensuel carte de {}",
     "est_ligne": traitement.est_debit_carte, "extraire": ia.extraire_carte,
     "ajouter": traitement.ajouter_carte, "libelle": traitement.libelle_carte,
     "controle": traitement.controle_carte, "tableau": traitement.tableau_carte,
     "tableau_liste": traitement.tableau_cartes, "total": lambda c: c["total_net"]},
    {"nom": "lcr", "liste": "lcrs", "lien": "lcr", "sens": "debit",
     "singulier": "relevé de LCR", "pluriel": "relevés de LCR",
     "ligne": "relevé LCR", "elements": "effets",
     "legende": "Le détail d'une ligne « relevé LCR » : les effets payés à vos fournisseurs.",
     "titre_detail": "Détail du relevé LCR de {}",
     "est_ligne": traitement.est_debit_lcr, "extraire": ia.extraire_lcr,
     "ajouter": traitement.ajouter_lcr, "libelle": traitement.libelle_lcr,
     "controle": traitement.controle_lcr, "tableau": traitement.tableau_lcr,
     "tableau_liste": traitement.tableau_lcrs, "total": lambda lcr: lcr["total"]},
    {"nom": "remise", "liste": "remises", "lien": "remise", "sens": "credit",
     "singulier": "bordereau de remise", "pluriel": "bordereaux de remise",
     "ligne": "remise chèque", "elements": "chèques",
     "legende": "Le détail d'une ligne « remise chèque » : les chèques de vos clients "
                "(documents scannés acceptés).",
     "titre_detail": "Détail de la remise de chèques de {}",
     "est_ligne": traitement.est_remise_cheques, "extraire": ia.extraire_remise,
     "ajouter": traitement.ajouter_remise, "libelle": traitement.libelle_remise,
     "controle": traitement.controle_remise, "tableau": traitement.tableau_remise,
     "tableau_liste": traitement.tableau_remises, "total": lambda r: r["total"]},
]


def afficher_detail(op, j):
    """Détail d'une ligne du relevé de banque : les paiements de son justificatif `j`."""
    st.subheader(j["titre_detail"].format(euros(op.get(j["sens"]) or 0)))
    detail = op.get(j["lien"])
    if not detail:
        st.info(f"Le {j['singulier']} de cette ligne n'a pas été importé. "
                "Ajoutez-le dans l'onglet « Ajouter un relevé ».")
        return
    st.caption(f"{majuscule(j['singulier'])} {j['libelle'](detail)}")
    _, ecart = j["controle"](detail)
    if abs(ecart) < 0.01:
        st.success(f"La somme des {j['elements']} correspond au total du {j['singulier']}.")
    else:
        st.error(f"Écart de {euros(ecart)} entre le total du {j['singulier']} et la somme de "
                 "ses lignes : il manque probablement une ligne.")
    afficher_tableau(j["tableau"](detail), "Facture retrouvée")


def afficher_liste_justificatifs(j):
    """Les justificatifs de la sorte `j` déjà importés : tableau, avertissement pour ceux
    qui ne correspondent à aucune ligne du relevé de banque, et suppression."""
    details = st.session_state[j["liste"]]
    if not details:
        return
    st.subheader(f"{majuscule(j['pluriel'])} importés")
    for detail in traitement.sans_ligne(operations, details, j["lien"]):
        st.warning(f"Le {j['singulier']} {j['libelle'](detail)} de "
                   f"{euros(j['total'](detail))} ne correspond à aucune ligne « {j['ligne']} » "
                   "du relevé de banque : le relevé de banque de ce mois n'est peut-être "
                   "pas importé.")
    afficher_tableau(j["tableau_liste"](details, operations), "Contrôle du total")
    with st.expander(f"Supprimer un {j['singulier']}"):
        choix = st.selectbox(majuscule(j["singulier"]), range(len(details)),
                             format_func=lambda i: j["libelle"](details[i]),
                             key=f"suppression_{j['nom']}")
        if st.button(f"Supprimer ce {j['singulier']}", key=f"supprimer_{j['nom']}"):
            details.pop(choix)
            sauver()
            st.rerun()


def importer_justificatifs(j):
    """Dépôt de PDF d'une sorte de justificatif : Claude les lit, chacun est ajouté à sa
    place par date, sauf s'il est déjà importé."""
    st.subheader(majuscule(j["pluriel"]))
    st.caption(j["legende"])
    fichiers = st.file_uploader(f"Déposez vos {j['pluriel']} PDF", type="pdf",
                                accept_multiple_files=True, key=f"fichiers_{j['nom']}")
    if not (fichiers and st.button(f"Analyser les {j['pluriel']}", key=f"analyser_{j['nom']}")):
        return
    details = st.session_state[j["liste"]]
    messages = []
    for fichier in fichiers:
        with st.spinner(f"Lecture de {fichier.name}…"):
            try:
                nouveau = j["extraire"](CLE_IA, fichier)
            except Exception as erreur:
                messages.append(("error", f"{fichier.name} : {erreur}"))
                continue
        if j["ajouter"](details, nouveau):
            messages.append(("success", f"{fichier.name} : {j['singulier']} ajouté."))
        else:
            messages.append(("warning", f"{fichier.name} : ce {j['singulier']} est déjà "
                                        "importé, il n'a pas été ajouté."))
    sauver()
    st.session_state.messages_releve = messages
    st.rerun()


with st.sidebar:
    st.title("📂 BELGALANE")
    st.divider()
    if MODE_DEMO:
        st.info("Mode démo : données du cahier des charges, aucune IA appelée.")
    else:
        st.success("IA Claude active.")
    # Seulement dans le bloc « Mes banques » : la page choisie est déjà connue ici.
    if st.session_state.get("page") == "Mes banques":
        for titre, detail in trous_releves:
            afficher_alerte(titre, detail)
    if MOT_DE_PASSE and st.button("Déconnexion"):
        st.session_state.clear()
        st.rerun()
    # Les petites fenêtres d'avertissement (doublons refusés) s'affichent au milieu de
    # l'écran, bien visibles, au lieu d'un coin. Ce style est ici, et non dans la page,
    # pour rester en place quand la page change.
    st.markdown("""
        <style>
        [data-testid="stToastContainer"] {
            top: 50% !important;
            bottom: auto !important;
            left: 50% !important;
            right: auto !important;
            width: auto !important;
            margin: 0 !important;
            transform: translate(-50%, -50%);
        }
        [data-testid="stToast"] {
            width: min(34rem, 90vw) !important;
            border: 2px solid rgb(230, 150, 30);
            box-shadow: 0 0.5rem 2rem rgba(0, 0, 0, 0.35);
        }
        [data-testid="stToastText"], [data-testid="stToastText"] p {
            font-size: 1.15rem !important;
            font-weight: 600;
        }
        </style>
    """, unsafe_allow_html=True)

# Les tuiles de l'accueil : (clé du bouton, texte, page ouverte).
TUILES = [
    ("tuile_achats", "🛒 Mes achats", "Mes achats"),
    ("tuile_ventes", "💰 Mes ventes", "Mes ventes"),
    ("tuile_banques", "🏦 Mes banques", "Mes banques"),
    ("tuile_dashboard", "📊 Mon dashboard", "Mon dashboard"),
]


def aller_a(nom_page):
    """Clic sur une tuile : ouvre la page choisie (le menu la sélectionne)."""
    st.session_state.page = nom_page


# Menu en haut de la page (et non plus dans la barre latérale),
# pour qu'il reste visible sur téléphone.
page = st.radio("Menu", ["Accueil", "Mes achats", "Mes ventes", "Mes banques",
                         "Mon dashboard"],
                key="page", horizontal=True, label_visibility="collapsed")

# ---------- Accueil ----------
if page == "Accueil":
    st.header("Accueil")
    # Chaque tuile a sa couleur (--accent) ; le reste du style est commun.
    st.markdown("""
        <style>
        .st-key-tuile_achats { --accent: 232, 131, 58; }
        .st-key-tuile_ventes { --accent: 46, 160, 67; }
        .st-key-tuile_banques { --accent: 59, 130, 246; }
        .st-key-tuile_dashboard { --accent: 139, 92, 246; }
        .st-key-accueil button {
            min-height: 9rem;
            border: 2px solid rgb(var(--accent));
            border-radius: 1rem;
            background-color: rgba(var(--accent), 0.14);
        }
        .st-key-accueil button:hover {
            border-color: rgb(var(--accent));
            background-color: rgba(var(--accent), 0.28);
            color: inherit;
        }
        .st-key-accueil button p { font-size: 1.7rem; font-weight: 600; }
        </style>
    """, unsafe_allow_html=True)
    with st.container(key="accueil"):
        for ligne in (TUILES[:2], TUILES[2:]):
            for colonne, (cle, texte, destination) in zip(st.columns(2), ligne):
                colonne.button(texte, key=cle, on_click=aller_a, args=(destination,),
                               width="stretch")

# ---------- Mes achats ----------
elif page == "Mes achats":
    st.header("Mes achats")
    onglet_liste, onglet_ajout = st.tabs(["Mes dépenses", "Ajouter dépenses"])

    with onglet_liste:
        if not factures:
            st.write("Aucune dépense n'a été ajoutée. "
                     "Ouvrez l'onglet « Ajouter dépenses » pour importer vos factures.")
        else:
            df = traitement.tableau_achats(factures, releve is not None)
            afficher_tableau(df, "Retrouvé en banque")
            st.download_button("Exporter en CSV", traitement.en_csv(df),
                               "mes_achats.csv", "text/csv")

            with st.expander("Supprimer une facture"):
                choix = st.selectbox(
                    "Facture", range(len(factures)),
                    format_func=lambda i: f"{factures[i]['fournisseur']} – "
                                          f"{factures[i]['fichier']}")
                if st.button("Supprimer cette facture"):
                    factures.pop(choix)
                    sauver()
                    st.rerun()

    with onglet_ajout:
        if MODE_DEMO:
            st.info("L'import de factures s'active quand la clé Anthropic est configurée. "
                    "En mode démo, les factures du cahier des charges sont déjà chargées.")
        else:
            fichiers = st.file_uploader("Déposez vos factures PDF", type="pdf",
                                        accept_multiple_files=True)
            if fichiers and st.button("Analyser les factures"):
                deja_la = []
                for fichier in fichiers:
                    with st.spinner(f"Lecture de {fichier.name}…"):
                        try:
                            nouvelle = ia.extraire_facture(CLE_IA, fichier)
                        except Exception as erreur:
                            st.error(f"{fichier.name} : {erreur}")
                            continue
                    if traitement.ajouter_facture(factures, nouvelle):
                        st.success(f"{fichier.name} : ajoutée.")
                    else:
                        deja_la.append(fichier.name)
                sauver()
                if deja_la:
                    prevenir_doublons(deja_la, "Mes achats")
                st.info("Ouvrez l'onglet « Mes dépenses » pour voir le résultat.")

# ---------- Mes ventes ----------
elif page == "Mes ventes":
    st.header("Mes ventes")
    onglet_liste, onglet_ajout = st.tabs(["Mes ventes", "Ajouter ventes"])

    with onglet_liste:
        if not ventes:
            st.write("Aucune vente n'a été ajoutée. "
                     "Ouvrez l'onglet « Ajouter ventes » pour importer vos factures de vente.")
        else:
            df = traitement.tableau_ventes(ventes, releve is not None)
            afficher_tableau(df, "Retrouvé en banque")
            st.download_button("Exporter en CSV", traitement.en_csv(df),
                               "mes_ventes.csv", "text/csv")

            with st.expander("Supprimer une facture de vente"):
                choix = st.selectbox(
                    "Facture de vente", range(len(ventes)),
                    format_func=lambda i: f"{ventes[i]['client']} – "
                                          f"{ventes[i]['numero_facture'] or ventes[i]['fichier']}")
                if st.button("Supprimer cette facture de vente"):
                    ventes.pop(choix)
                    sauver()
                    st.rerun()

    with onglet_ajout:
        if MODE_DEMO:
            st.info("L'import de factures s'active quand la clé Anthropic est configurée. "
                    "En mode démo, des ventes d'exemple sont déjà chargées.")
        else:
            fichiers = st.file_uploader("Déposez vos factures de vente PDF", type="pdf",
                                        accept_multiple_files=True)
            if fichiers and st.button("Analyser les factures de vente"):
                deja_la = []
                for fichier in fichiers:
                    with st.spinner(f"Lecture de {fichier.name}…"):
                        try:
                            nouvelle = ia.extraire_vente(CLE_IA, fichier)
                        except Exception as erreur:
                            st.error(f"{fichier.name} : {erreur}")
                            continue
                    if traitement.ajouter_facture(ventes, nouvelle, "client"):
                        st.success(f"{fichier.name} : ajoutée.")
                    else:
                        deja_la.append(fichier.name)
                sauver()
                if deja_la:
                    prevenir_doublons(deja_la, "Mes ventes")
                st.info("Ouvrez l'onglet « Mes ventes » pour voir le résultat.")

# ---------- Mes banques ----------
elif page == "Mes banques":
    st.header("Mes banques")
    onglet_releve, onglet_ajout = st.tabs(["Mon relevé", "Ajouter un relevé"])

    with onglet_releve:
        if not releve:
            st.write("Aucun relevé n'a été ajouté. "
                     "Ouvrez l'onglet « Ajouter un relevé » pour importer votre relevé.")
        else:
            # Le titre porte le nom de la banque lue sur les relevés.
            banques = ", ".join(dict.fromkeys(r["banque"] for r in releves if r.get("banque")))
            st.subheader(f"Mes relevés de banque {banques}".strip())
            calcule, ecart = traitement.controle_solde(releve)
            col1, col2, col3 = st.columns(3)
            col1.metric("Solde début (lu)", euros(releve["solde_debut"]))
            col2.metric("Solde fin (lu)", euros(releve["solde_fin"]))
            col3.metric("Solde fin (calculé)", euros(calcule))
            if abs(ecart) < 0.01:
                if not trous_releves:
                    st.success("Soldes cohérents : aucune opération ne manque.")
            else:
                st.error(f"Écart de {euros(ecart)} entre le solde lu et le solde calculé : "
                         "il manque probablement un relevé ou une opération.")
            df = traitement.tableau_banque(releve)
            lignes_detail = [i for i, op in enumerate(operations)
                             if traitement.est_ligne_detaillee(op)]
            if lignes_detail:
                st.caption("Cliquez sur une ligne « débit mensuel carte », « relevé LCR » ou "
                           "« remise chèque » pour voir son détail.")
            ligne = afficher_tableau(df, "Facture retrouvée", cle_selection="tableau_banque",
                                     lignes_en_gras=lignes_detail)
            if ligne is not None and ligne < len(operations):
                for j in JUSTIFICATIFS:
                    if j["est_ligne"](operations[ligne]):
                        afficher_detail(operations[ligne], j)
                        break
            st.download_button("Exporter en CSV", traitement.en_csv(df),
                               "ma_banque.csv", "text/csv")

        # Les relevés importés, sur le même modèle que les relevés de carte, de LCR et les
        # bordereaux de remise qui suivent : un titre, un tableau, la suppression.
        if releves:
            st.subheader("Relevés de banque importés")
            afficher_tableau(traitement.tableau_releves(releves), "Contrôle du solde")
            with st.expander("Supprimer un relevé de banque"):
                choix = st.selectbox("Relevé de banque", range(len(releves)),
                                     format_func=lambda i: traitement.libelle_releve(releves[i]),
                                     key="suppression_releve")
                if st.button("Supprimer ce relevé de banque", key="supprimer_releve"):
                    releves.pop(choix)
                    sauver()
                    st.rerun()

        for j in JUSTIFICATIFS:
            afficher_liste_justificatifs(j)

    with onglet_ajout:
        if MODE_DEMO:
            st.info("L'import de relevés s'active quand la clé Anthropic est configurée. "
                    "En mode démo, le relevé CIC du cahier des charges est déjà chargé.")
        else:
            # Résultat de l'import précédent, gardé le temps du rechargement de la page.
            for genre, texte in st.session_state.pop("messages_releve", []):
                getattr(st, genre)(texte)
            st.subheader("Relevés de compte")
            fichiers = st.file_uploader("Déposez vos relevés PDF", type="pdf",
                                        accept_multiple_files=True)
            if fichiers and st.button("Analyser les relevés"):
                messages = []
                for fichier in fichiers:
                    with st.spinner(f"Lecture de {fichier.name}…"):
                        try:
                            nouveau = ia.extraire_releve(CLE_IA, fichier)
                        except Exception as erreur:
                            messages.append(("error", f"{fichier.name} : {erreur}"))
                            continue
                    # Un relevé déjà importé n'est pas ajouté ; un nouveau prend sa place
                    # par date, sans remplacer les autres.
                    if traitement.ajouter_releve(releves, nouveau):
                        messages.append(("success", f"{fichier.name} : relevé ajouté."))
                    else:
                        messages.append(("warning", f"{fichier.name} : ce relevé est déjà "
                                                    "importé, il n'a pas été ajouté."))
                sauver()
                st.session_state.messages_releve = messages
                st.rerun()

            for j in JUSTIFICATIFS:
                importer_justificatifs(j)

# ---------- Mon dashboard ----------
else:
    st.header("Mon dashboard")
    if not releve:
        st.write("Le dashboard a besoin d'un relevé de banque. "
                 "Ajoutez-en un dans « Mes banques ».")
    else:
        _, ecart = traitement.controle_solde(releve)
        if abs(ecart) >= 0.01:
            st.error("Le contrôle de solde du relevé échoue : voir « Mes banques ».")

        st.subheader("Achats")
        df = traitement.tableau_dashboard(releve, cartes, lcrs)
        manquantes = df[df["Facture retrouvée"] == "FACTURE MANQUANTE"]
        non_payees = [f for f in factures if not f["doublon"] and not f["retrouve"]]

        col1, col2, col3 = st.columns(3)
        col1.metric("Factures manquantes", len(manquantes),
                    help="Paiements fournisseurs sans facture importée")
        col2.metric("Montant non justifié", euros(-manquantes["Montant en banque"].sum()))
        col3.metric("Factures non retrouvées en banque", len(non_payees),
                    help="Factures importées sans paiement correspondant")

        st.caption("Cette partie reprend uniquement les paiements fournisseurs du relevé de "
                   "banque et, en plus, le détail des relevés de carte et de LCR (colonne "
                   "« Paiement »).")
        afficher_tableau(df, "Facture retrouvée")
        st.download_button("Exporter en CSV", traitement.en_csv(df),
                           "dashboard.csv", "text/csv")

        st.subheader("Ventes")
        df = traitement.tableau_dashboard_ventes(releve, remises)
        sans_facture = df[df["Facture retrouvée"] == "FACTURE MANQUANTE"]
        non_encaissees = [v for v in ventes if not v["doublon"] and not v["retrouve"]]

        col1, col2, col3 = st.columns(3)
        col1.metric("Factures manquantes", len(sans_facture),
                    help="Encaissements clients sans facture de vente importée")
        col2.metric("Montant non justifié", euros(sans_facture["Montant en banque"].sum()))
        col3.metric("Factures non retrouvées en banque", len(non_encaissees),
                    help="Factures de vente importées sans encaissement correspondant")

        st.caption("Cette partie reprend uniquement les encaissements clients du relevé de "
                   "banque et, en plus, le détail des remises de chèques (colonne « Paiement »).")
        afficher_tableau(df, "Facture retrouvée")
        st.download_button("Exporter en CSV", traitement.en_csv(df),
                           "dashboard_ventes.csv", "text/csv", key="csv_dashboard_ventes")