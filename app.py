"""BELGALANE : achats, banque et rapprochement, avec l'IA Mistral.

Lancer en local : streamlit run app.py
"""

import copy

import streamlit as st

import ia
import sample_data
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
    st.title("BELGALANE")
    saisie = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter"):
        if saisie == MOT_DE_PASSE:
            st.session_state.connecte = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()

# ---------- Mode démo ou IA ----------
CLE_MISTRAL = lire_secret("MISTRAL_API_KEY")
MODE_DEMO = not CLE_MISTRAL

if "factures" not in st.session_state:
    if MODE_DEMO:
        st.session_state.factures = copy.deepcopy(sample_data.FACTURES_DEMO)
        st.session_state.releve = copy.deepcopy(sample_data.RELEVE_BANCAIRE_DEMO)
    else:
        st.session_state.factures = []
        st.session_state.releve = None

factures = st.session_state.factures
releve = st.session_state.releve

# Recalculé à chaque affichage : un relevé ajouté plus tard met
# automatiquement à jour la colonne « Retrouvé en banque ».
traitement.marquer_doublons(factures)
traitement.rapprocher(factures, releve["operations"] if releve else [])

# ---------- Affichage ----------
COULEURS = {
    "OUI": "background-color: rgba(46, 160, 67, 0.22)",
    "NON": "background-color: rgba(218, 54, 51, 0.22)",
    "FACTURE MANQUANTE": "background-color: rgba(218, 54, 51, 0.22)",
    "DOUBLON": "background-color: rgba(230, 150, 30, 0.25)",
}


def afficher_tableau(df, colonne_statut):
    def couleur_ligne(ligne):
        return [COULEURS.get(ligne[colonne_statut], "")] * len(ligne)

    colonnes_nombres = df.select_dtypes("number").columns
    style = (df.style
             .apply(couleur_ligne, axis=1)
             .format(precision=2, decimal=",", thousands=" ", na_rep="—",
                     subset=colonnes_nombres))
    st.dataframe(style, hide_index=True, width="stretch")


def euros(montant):
    return f"{montant:,.2f} €".replace(",", " ").replace(".", ",")


with st.sidebar:
    st.title("BELGALANE")
    st.divider()
    if MODE_DEMO:
        st.info("Mode démo : données du cahier des charges, aucune IA appelée.")
    else:
        st.success("IA Mistral active.")
    if MOT_DE_PASSE and st.button("Déconnexion"):
        st.session_state.clear()
        st.rerun()

# Menu en haut de la page (et non plus dans la barre latérale),
# pour qu'il reste visible sur téléphone.
page = st.radio("Menu", ["Mes achats", "Mes banques", "Mon dashboard"],
                horizontal=True, label_visibility="collapsed")

# ---------- Mes achats ----------
if page == "Mes achats":
    st.header("Mes achats")
    onglet_liste, onglet_ajout = st.tabs(["Mes dépenses", "Ajouter dépenses"])

    with onglet_liste:
        if not factures:
            st.write("Aucune dépense n'a été ajoutée. "
                     "Ouvrez l'onglet « Ajouter dépenses » pour importer vos factures.")
        else:
            nb_doublons = sum(f["doublon"] for f in factures)
            if nb_doublons:
                st.warning(f"Attention : {nb_doublons} doublon(s) détecté(s), "
                           "en orange dans le tableau. Ils sont ignorés dans le rapprochement.")
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
                    st.rerun()

    with onglet_ajout:
        if MODE_DEMO:
            st.info("L'import de factures s'active quand la clé Mistral est configurée. "
                    "En mode démo, les factures du cahier des charges sont déjà chargées.")
        else:
            fichiers = st.file_uploader("Déposez vos factures PDF", type="pdf",
                                        accept_multiple_files=True)
            if fichiers and st.button("Analyser les factures"):
                for fichier in fichiers:
                    with st.spinner(f"Lecture de {fichier.name}…"):
                        try:
                            factures.append(ia.extraire_facture(CLE_MISTRAL, fichier))
                            st.success(f"{fichier.name} : ajoutée.")
                        except Exception as erreur:
                            st.error(f"{fichier.name} : {erreur}")
                st.info("Ouvrez l'onglet « Mes dépenses » pour voir le résultat.")

# ---------- Mes banques ----------
elif page == "Mes banques":
    st.header("Mes banques")
    onglet_releve, onglet_ajout = st.tabs(["Mon relevé", "Ajouter un relevé"])

    with onglet_releve:
        if not releve:
            st.write("Aucun relevé n'a été ajouté. "
                     "Ouvrez l'onglet « Ajouter un relevé » pour importer votre relevé.")
        else:
            calcule, ecart = traitement.controle_solde(releve)
            col1, col2, col3 = st.columns(3)
            col1.metric("Solde début (lu)", euros(releve["solde_debut"]))
            col2.metric("Solde fin (lu)", euros(releve["solde_fin"]))
            col3.metric("Solde fin (calculé)", euros(calcule))
            if abs(ecart) < 0.01:
                st.success("Soldes cohérents : aucune opération ne manque.")
            else:
                st.error(f"Écart de {euros(ecart)} entre le solde lu et le solde calculé : "
                         "il manque probablement un relevé ou une opération.")
            df = traitement.tableau_banque(releve)
            afficher_tableau(df, "Facture retrouvée")
            st.download_button("Exporter en CSV", traitement.en_csv(df),
                               "ma_banque.csv", "text/csv")

    with onglet_ajout:
        if MODE_DEMO:
            st.info("L'import de relevés s'active quand la clé Mistral est configurée. "
                    "En mode démo, le relevé CIC du cahier des charges est déjà chargé.")
        else:
            fichier = st.file_uploader("Déposez votre relevé PDF", type="pdf")
            if fichier and st.button("Analyser le relevé"):
                with st.spinner(f"Lecture de {fichier.name}…"):
                    try:
                        st.session_state.releve = ia.extraire_releve(CLE_MISTRAL, fichier)
                        st.success(f"{fichier.name} : relevé ajouté. "
                                   "Il remplace le relevé précédent.")
                    except Exception as erreur:
                        st.error(f"{fichier.name} : {erreur}")

# ---------- Mon dashboard ----------
else:
    st.header("Mon dashboard")
    if not releve:
        st.write("Le dashboard a besoin d'un relevé de banque. "
                 "Ajoutez-en un dans « Mes banques ».")
    else:
        df = traitement.tableau_dashboard(releve)
        manquantes = df[df["Facture retrouvée"] == "FACTURE MANQUANTE"]
        non_payees = [f for f in factures if not f["doublon"] and not f["retrouve"]]
        _, ecart = traitement.controle_solde(releve)

        col1, col2, col3 = st.columns(3)
        col1.metric("Factures manquantes", len(manquantes),
                    help="Paiements fournisseurs sans facture importée")
        col2.metric("Montant non justifié", euros(-manquantes["Montant en banque"].sum()))
        col3.metric("Factures non retrouvées en banque", len(non_payees),
                    help="Factures importées sans paiement correspondant")
        if abs(ecart) >= 0.01:
            st.error("Le contrôle de solde du relevé échoue : voir « Mes banques ».")

        st.caption("Le dashboard reprend uniquement les paiements fournisseurs du relevé.")
        afficher_tableau(df, "Facture retrouvée")
        st.download_button("Exporter en CSV", traitement.en_csv(df),
                           "dashboard.csv", "text/csv")
