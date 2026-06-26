from app.config import charger_config


def test_defauts_quand_fichier_absent(tmp_path):
    cfg = charger_config(tmp_path / "absent.yaml")
    assert cfg["model_defaut"] == "claude-sonnet-4-6"
    assert cfg["model_escalade"] == "claude-opus-4-8"
    assert cfg["seuil_reconciliation_pct"] == 1.0


def test_override_depuis_yaml(tmp_path):
    p = tmp_path / "config.local.yaml"
    p.write_text("seuil_reconciliation_pct: 2.5\nanthropic_api_key: cle\n", encoding="utf-8")
    cfg = charger_config(p)
    assert cfg["seuil_reconciliation_pct"] == 2.5
    assert cfg["anthropic_api_key"] == "cle"
    assert cfg["model_defaut"] == "claude-sonnet-4-6"  # défaut conservé


def test_defauts_seuils_matching(tmp_path):
    cfg = charger_config(tmp_path / "absent.yaml")
    assert cfg["seuil_match_bas"] == 0.80
    assert cfg["seuil_match_auto"] == 0.95
