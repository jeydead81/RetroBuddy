from pathlib import Path

import yaml

DEFAUTS = {
    "model_defaut": "claude-sonnet-4-6",
    "model_escalade": "claude-opus-4-8",
    "seuil_reconciliation_pct": 1.0,
    "seuil_match_bas": 0.80,
    "seuil_match_auto": 0.95,
}


def charger_config(chemin="config.local.yaml"):
    cfg = dict(DEFAUTS)
    p = Path(chemin)
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        cfg.update({k: v for k, v in data.items() if v is not None})
    return cfg


def enregistrer_cle_api(cle, chemin="config.local.yaml"):
    """Écrit/met à jour la clé API dans config.local.yaml (gitignored), sans toucher
    aux autres réglages déjà présents."""
    p = Path(chemin)
    data = {}
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    data["anthropic_api_key"] = cle
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                 encoding="utf-8")
