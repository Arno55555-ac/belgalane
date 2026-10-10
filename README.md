# BELGALANE

Application de pré-comptabilisation pour TPE : l'IA Mistral (Ministral 8B) lit les factures d'achat et les relevés de banque en PDF, puis le programme rapproche les deux et signale les factures manquantes.

Périmètre : achats + banque + rapprochement, PDF générés par logiciel uniquement (pas de scans, pas de photos, pas de ventes).

## Les fichiers

- `app.py` : l'interface (Mes achats, Mes banques, Mon dashboard) et le mot de passe.
- `traitement.py` : doublons, rapprochement, contrôle de solde, tableaux et export CSV. Pur calcul Python, sans IA.
- `ia.py` : lecture du texte des PDF (pypdf) et extraction en JSON par Mistral.
- `sample_data.py` : les factures et le relevé du cahier des charges, pour le mode démo.
- `requirements.txt` : les bibliothèques à installer.
- `.gitignore` : empêche d'envoyer les secrets sur GitHub.

## Les deux modes

Sans clé Mistral, l'app est en **mode démo** : elle charge les données du cahier des charges et n'appelle aucune IA, donc rien n'est consommé.
Avec une clé `MISTRAL_API_KEY`, l'import de PDF s'active.

## Lancer en local

```
pip install -r requirements.txt
streamlit run app.py
```

## Secrets (facultatifs)

Créer le fichier `.streamlit/secrets.toml` :

```
APP_PASSWORD = "votre-mot-de-passe"
MISTRAL_API_KEY = "votre-cle-mistral"
```

En ligne, mettre les mêmes lignes dans Streamlit Community Cloud → votre app → Settings → Secrets.
Sans `APP_PASSWORD`, l'app n'est pas protégée.

## Limites connues du MVP

Les données sont gardées en mémoire le temps de la session : elles disparaissent si on recharge la page. Un seul relevé est géré à la fois.
