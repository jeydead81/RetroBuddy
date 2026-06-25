"""Test d'intégration : appelle la vraie API. Lancer avec :
    .venv/Scripts/python -m pytest -m integration
Nécessite config.local.yaml (clé) et au moins un PDF dans data/samples/factures_labo/.
"""
from pathlib import Path

import pytest

from app.config import charger_config
from app.temps1.extraction_ia import ClaudeExtractor
from app.temps1.pdf_reader import lire_pdf

SAMPLES = Path("data/samples/factures_labo")


@pytest.mark.integration
def test_extraction_reelle_premier_pdf():
    cfg = charger_config()
    if not cfg.get("anthropic_api_key"):
        pytest.skip("clé API absente de config.local.yaml")
    pdfs = sorted(SAMPLES.glob("*.pdf")) if SAMPLES.exists() else []
    if not pdfs:
        pytest.skip("aucun PDF dans data/samples/factures_labo/")

    ex = ClaudeExtractor(cfg["anthropic_api_key"])
    facture = ex.extraire(lire_pdf(pdfs[0]), cfg["model_defaut"])

    assert facture.type_document in {
        "facture_marchandise", "avoir", "abonnement_service", "releve", "autre"}
