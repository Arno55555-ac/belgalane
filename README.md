# BELGALANE

Application de pré-comptabilisation pour TPE : l'IA Claude lit en PDF (même scannés) les factures d'achat et de vente, les relevés de banque et leurs justificatifs, puis le programme rapproche le tout et signale les factures manquantes.

## Ce que fait l'app

- **Mes achats** et **Mes ventes** : import des factures PDF, doublons refusés à l'import, statut « retrouvé en banque », export CSV.
- **Mes banques** : plusieurs relevés rangés par date (doublon refusé, avertissement quand un relevé intermédiaire manque) et, pour les lignes qui regroupent plusieurs paiements, leur justificatif : relevé de carte (« débit mensuel carte »), relevé de LCR, bordereau de remise de chèques. Un clic sur la ligne affiche le détail, chaque paiement étant rapproché d'une facture.
- **Mon dashboard** : achats et ventes rapprochés du relevé (colonne « Paiement » : Compte, Carte, LCR ou Chèque), factures manquantes, montants non justifiés, export CSV.

## Les fichiers

- `app.py` : l'interface et le mot de passe.
- `traitement.py` : doublons, rapprochement, contrôles de totaux, tableaux et export CSV. Pur calcul Python, sans IA.
- `ia.py` : envoie les PDF à Claude (`claude-sonnet-5-5`), qui renvoie les données au format JSON.
- `stockage.py` : sauvegarde des données dans une base SQLite locale (`donnees/belgalane.db`, jamais publiée).
- `sample_data.py` : les données du cahier des charges, pour le mode démo.
- `requirements.txt` : les bibliothèques à installer.
- `.gitignore` : empêche d'envoyer les secrets et la base de données sur GitHub.

## Les deux modes

Sans clé Anthropic, l'app est en **mode démo** : elle charge les données du cahier des charges, n'appelle aucune IA, n'enregistre rien et l'import de PDF est désactivé.
Avec une clé `ANTHROPIC_API_KEY`, l'import de PDF s'active (chaque lecture est payante) et les données sont enregistrées.

## Lancer en local

```
pip install -r requirements.txt
streamlit run app.py
```

## Secrets (facultatifs)

Créer le fichier `.streamlit/secrets.toml` :

```
APP_PASSWORD = "votre-mot-de-passe"
ANTHROPIC_API_KEY = "votre-cle-anthropic"
```

En ligne, mettre les mêmes lignes dans Streamlit Community Cloud → votre app → Settings → Secrets.
Sans `APP_PASSWORD`, l'app n'est pas protégée.

## Règles de rapprochement

Une facture est retrouvée quand un paiement a le même montant TTC, à 15 jours près. Pour les effets de LCR et les chèques remis, payés plus tard, l'écart accepté est de 90 jours.

## Limites connues

- Les données enregistrées vivent dans un fichier local : sur Streamlit Community Cloud, il est effacé à chaque redémarrage ou redéploiement.
- Un seul compte bancaire est géré.
- Pas de comptes utilisateurs : une seule base pour toute l'app.
