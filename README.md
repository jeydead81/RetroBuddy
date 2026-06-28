<div align="center">
  <img src="Logo.png" alt="RetroBuddy" width="160">

  # RetroBuddy

  **L'outil qui automatise vos factures de rétrocession inter-pharmacies.** 🌴
</div>

---

À partir des **factures laboratoires** (le coût réel des produits) et des
**factures de vente rétrocession du LGO (LGPI)**, l'outil construit un référentiel de prix,
rapproche chaque ligne et calcule le prix de rétrocession au **dernier prix net connu à la
date du bon de livraison**.

Principe directeur : **aucune erreur permise sur le montant facturé.** Tout ce qui n'est pas
certain est signalé pour vérification (rouge / orange / facture bloquée), jamais inventé ni
masqué. C'est une **application web locale** (sur votre ordinateur) avec une base **dans un
simple fichier** — pas de cloud, pas de compte, pas de serveur distant (hors les appels à
l'IA qui lit les PDF).

---

# 🚀 Installation

> Sous **Windows**. Comptez ~10 minutes la première fois.

## 1. Récupérer RetroBuddy

Sur la [page GitHub](https://github.com/jeydead81/RetroBuddy), clique sur le bouton vert **« Code › Download ZIP »**, puis **extrais** le dossier (clic droit › *Extraire tout…*) où tu veux — par exemple sur le Bureau. **Pas besoin de compte GitHub ni de Git.**

## 2. Installer

Ouvrez le dossier `RetroBuddy` et **double-cliquez sur `installer.bat`**. Il s'occupe de tout :
- s'il manque **Python**, il ouvre la page de téléchargement → installez-le en **cochant bien « Add python.exe to PATH »**, puis relancez `installer.bat` ;
- il installe les composants nécessaires ;
- il crée un **raccourci « RetroBuddy » sur votre bureau**.

> 💡 Si Windows affiche *« Windows a protégé votre PC »* : cliquez sur **« Informations complémentaires » › « Exécuter quand même »**.

## 3. Lancer

Double-cliquez sur le raccourci **RetroBuddy** du bureau. Le navigateur s'ouvre tout seul sur l'application.

> ⚠️ Une **fenêtre noire** s'ouvre aussi : **laissez-la ouverte** (c'est le moteur de l'app). Pour arrêter RetroBuddy, fermez-la.

## 4. Renseigner votre clé API (une seule fois)

Au premier lancement, l'accueil vous demande une **clé API Anthropic** (c'est l'IA qui lit vos PDF).

**Comment l'obtenir :**
1. Créez un compte sur **[console.anthropic.com](https://console.anthropic.com)**.
2. Ajoutez des crédits : menu **Billing** › ajoutez une carte / un montant (ex. 5 €).
3. Menu **API Keys** › **Create Key** › copiez la clé (elle commence par `sk-ant-…`).
4. Collez-la dans le bandeau de l'accueil RetroBuddy, **Enregistrer**. C'est tout — elle reste sur votre poste, n'est jamais partagée.

> 💸 **Coût** : chaque facture lue coûte ~**0,01 à 0,05 €**. Une grosse facture (plusieurs pages) un peu plus. Vous voyez le coût en direct dans l'app et pouvez le réinitialiser dans ⚙ Réglages.

---

# 🧭 Utilisation — le parcours guidé

L'accueil explique tout, et la barre du haut suit **l'ordre à respecter** :

| Étape | Onglet | Ce que vous faites |
|------|--------|--------------------|
| **1** | **Import labos** | Déposez vos PDF de factures **laboratoires**. RetroBuddy en extrait les prix et construit le référentiel. *(À faire en premier — sans ça, rien ne se rapproche.)* |
| **2** | **Import LGO** | Déposez la facture de **rétrocession (LGPI)**. Il la découpe par bon de livraison et rapproche chaque ligne. |
| **3** | **Résolution** | Les lignes **à compléter** (rouge) / **à confirmer** (orange) : édition à la volée, accepter/refuser un rapprochement. |
| **4** | **Factures LGPI** | La facture finale : aperçu, et **export PDF / Excel / CSV** *(bloqué tant qu'une ligne est à compléter ou qu'un contrôle échoue)*. |

Onglets de consultation : **Référentiel** (prix, modifiables à la main), **Factures labos**, **Lignes rétro**.
**⚙ Réglages** : votre clé API, **réinitialiser les compteurs de coût**, et **supprimer des données** (par catégorie, avec confirmation).

> 🛡️ **Fiabilité** : RetroBuddy vérifie que rien n'a été oublié (somme des lignes = total affiché), que la TVA et les quantités sont cohérentes, et **bloque la facture** au moindre doute. Une même facture LGO importée deux fois est signalée (**doublon**).

---

# 🔄 Mettre à jour

Double-clique sur **`update.bat`** : il télécharge la dernière version et l'installe. **Pas besoin de Git**, et **ta base de données + ta clé ne sont jamais touchées** (elles ne sont pas dans le téléchargement).

# 💾 Sauvegarde & partage

Dans **Factures labos**, *« ⤓ Exporter la base »* enregistre **tout** dans un fichier. Faites-le **avant une mise à jour** ou pour **copier vos données sur un autre poste / les partager** entre confrères (puis *Importer* de l'autre côté).

---

# 🛠️ Pour les développeurs

<details>
<summary>Installation manuelle, tests, architecture</summary>

### Pile technique
- **Python 3.13**, **FastAPI** + **uvicorn**, **SQLite** (intégré à Python).
- Extraction par **Claude** (lecture PDF native + sorties structurées Pydantic), **Sonnet 4.6**
  par défaut, **escalade Opus 4.8** quand les totaux ne réconcilient pas.

### Installation manuelle
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# Linux/macOS : .venv/bin/python -m pip install -r requirements.txt
```
La clé API se renseigne via l'UI (⚙ Réglages) ou dans `config.local.yaml` (gitignored).

### Lancer / tester
```bash
.venv/Scripts/python -m uvicorn app.main:app
.venv/Scripts/python -m pytest                    # unitaires (aucun appel réseau)
.venv/Scripts/python -m pytest -m integration     # extraction réelle (clé + PDF requis)
```

### Architecture (4 temps, tous terminés)
1. **Référentiel prix** : ingestion factures labo → classification → extraction IA → garde-fous → référentiel historisé.
2. **Rétrocession** : ingestion facture LGPI → matching par code → « dernier prix net ≤ date du BL ».
3. **Résolution** : matching par désignation, édition inline, ingestion en tâche de fond.
4. **Facture** : aperçu + exports PDF/Excel/CSV, **bloqués** si ligne rouge ou contrôle de cohérence en échec.

Garde-fous d'extraction : **complétude** (Σ lignes = total HT), **cohérence ligne** (qté × prix = montant), **TVA par taux**, **anti-troncature**, **anti-doublon**. Voir `CADRAGE_RETROCESSION.md` et `docs/superpowers/`.

> ⚠️ Le dépôt doit rester **public** pour que le « Download ZIP » et `update.bat` (téléchargement anonyme du ZIP de `main`) fonctionnent chez les confrères.

</details>
