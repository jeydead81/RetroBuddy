<div align="center">
  <img src="Logo.png" alt="RetroBuddy" width="160">

  # RetroBuddy

  **Automatisation des factures de rétrocession inter-pharmacies.**
</div>

---

RetroBuddy transforme un travail manuel d'environ 6 semaines/an en quelques heures de
validation. À partir des **factures laboratoires** (pour le coût réel des produits) et des
**factures de vente rétrocession du LGO**, l'outil construit un référentiel de prix, rapproche
chaque ligne par code, et calcule le prix de rétrocession au **dernier prix net connu à la date
du bon de livraison**.

Principe directeur : **aucune erreur permise sur le montant facturé.** Tout ce qui n'est pas
certain est signalé pour vérification, jamais masqué ni inventé.

C'est une **application web locale** (FastAPI sur `localhost`) avec une base **SQLite** dans un
simple fichier — pas de serveur distant, pas de comptes, pas de cloud (hors les appels d'API
d'extraction). Installable telle quelle chez chaque confrère ; la base se copie d'un poste à
l'autre.

## Architecture en 4 temps

| Temps | Rôle | Statut |
|-------|------|--------|
| **1** | Référentiel prix : ingestion des **factures labo** (PDF) → classification → extraction IA → garde-fous → référentiel prix historisé. | ✅ Terminé |
| **2** | Ingestion de la **facture LGO de rétrocession** → matching par code (passes 1-2) → calcul « dernier prix net ≤ date du BL ». | ✅ Terminé |
| **3** | Résolution des écarts : tableau type Excel, compteurs, couleurs rouge/orange, édition inline, matching par désignation (passes 3-5). | ⏳ À venir |
| **4** | Édition de la facture de rétrocession (PDF calqué LGO + Excel), export bloqué tant qu'une ligne rouge subsiste. | ⏳ À venir |

Cadrage métier complet : [`CADRAGE_RETROCESSION.md`](CADRAGE_RETROCESSION.md).
Specs & plans d'implémentation : [`docs/superpowers/`](docs/superpowers/).

## Pile technique

- **Python 3.13**, **FastAPI** + **uvicorn**, **SQLite** (intégré à Python).
- Extraction par **Claude** (lecture PDF native + sorties structurées Pydantic), modèle
  **Sonnet 4.6** par défaut avec **escalade Opus 4.8** sur les factures dont les totaux ne
  réconcilient pas.
- Tests : **pytest** (cœur métier testé sans appel réseau ; tests d'intégration marqués).

## Installation

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt      # Windows
# (Linux/macOS : .venv/bin/python -m pip install -r requirements.txt)
```

Configurer la clé API (jamais versionnée) :

```bash
cp config.example.yaml config.local.yaml
# puis éditer config.local.yaml et renseigner anthropic_api_key
```

> ⚠️ **Sécurité** : `config.local.yaml` et le dossier `data/` sont **gitignored**. Ne jamais
> committer de clé API ni de base de données. Voir `.gitignore`.

## Utilisation

Lancer l'application :

```bash
.venv/Scripts/python -m uvicorn app.main:app --reload
```

Puis ouvrir <http://127.0.0.1:8000>. Sous Windows, le script `lancer_retrobuddy.bat` (ou le
raccourci bureau) démarre le serveur et ouvre le navigateur automatiquement.

Onglets :
- **Import labo** — déposer les factures laboratoires (PDF). Compteur de progression + coût.
- **Référentiel** — les prix extraits, historisés par code et par date.
- **Factures** — statut de chaque facture (ingérée / ignorée / en revue) avec le motif.
- **Rétrocession** — déposer la facture LGO. Compteur + coût.
- **Lignes rétro** — chaque ligne rapprochée (resolu) ou signalée (rouge), par BL.

> Le matching cherche dans le référentiel : pour obtenir des rapprochements, ingérer d'abord les
> factures labo correspondantes, puis la facture LGO.

## Tests

```bash
.venv/Scripts/python -m pytest                   # tests unitaires (aucun appel réseau)
.venv/Scripts/python -m pytest -m integration    # extraction réelle (nécessite clé + PDF d'échantillon)
```

## Structure du projet

```
app/
  config.py            chargement config (clé API, seuils)
  db.py                schéma SQLite + migrations idempotentes
  codes/               validation CIP13/EAN13 (checksum), pont CIP<->EAN
  temps1/              référentiel prix : extraction labo, classification,
                       filtres, garde-fous, pipeline, coût
  temps2/              rétrocession : extraction LGO, matching, calcul prix,
                       normalisation des dates, orchestration
  main.py              FastAPI : routes + UI
  ui/                  templates HTML + statiques (logo/favicon)
prompts/               prompts d'extraction (A = labo, B = LGO)
tests/                 pytest
docs/superpowers/      specs & plans d'implémentation
data/                  base SQLite + échantillons (gitignored)
```

## Coût

Extraction via Claude Sonnet 4.6 (~0,01–0,05 $/facture selon la taille), escalade Opus 4.8
uniquement sur les cas signalés. Le coût réel est mesuré et affiché dans l'interface (par
fichier, par lot, cumulé).
