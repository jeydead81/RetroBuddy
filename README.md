# RetroBuddy

Automatisation des factures de rétrocession inter-pharmacies. Voir
`CADRAGE_RETROCESSION.md` pour le cadrage global.

## Temps 1 — Référentiel prix

1. `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt`
2. Copier `config.example.yaml` en `config.local.yaml` et renseigner la clé API.
3. Lancer les tests : `.venv/Scripts/python -m pytest`
4. Lancer l'app : `.venv/Scripts/python -m uvicorn app.main:app --reload`
