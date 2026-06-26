"""Test d'intégration LGO (vraie API). Lancer avec :
    .venv/Scripts/python -m pytest -m integration
Nécessite config.local.yaml (clé) et un PDF dans data/samples/factures_lgo/.
"""
from pathlib import Path

import pytest

from app.config import charger_config
from app.temps1.extraction_ia import ClaudeExtractor
from app.temps1.pdf_reader import lire_pdf
from app.temps2.schemas import RetroExtrait

SAMPLES = Path("data/samples/factures_lgo")


@pytest.mark.integration
def test_extraction_lgo_reelle():
    cfg = charger_config()
    if not cfg.get("anthropic_api_key"):
        pytest.skip("clé API absente")
    pdfs = sorted(SAMPLES.glob("*.pdf")) if SAMPLES.exists() else []
    if not pdfs:
        pytest.skip("aucun PDF dans data/samples/factures_lgo/")

    ex = ClaudeExtractor(cfg["anthropic_api_key"],
                         prompt_path="prompts/extraction_retro.txt",
                         output_format=RetroExtrait)
    retro = ex.extraire(lire_pdf(pdfs[0]), cfg["model_defaut"])

    assert retro.type_document == "retro_lgo"
    assert retro.lignes, "au moins une ligne extraite"
    l = retro.lignes[0]
    assert l.bl_date is not None
    assert l.tva in (2.1, 5.5, 10.0, 20.0)
