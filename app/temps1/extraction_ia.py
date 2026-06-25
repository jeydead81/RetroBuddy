from typing import Protocol

from app.temps1.pdf_reader import PdfDocument
from app.temps1.schemas import FactureExtraite


class Extractor(Protocol):
    def extraire(self, pdf: PdfDocument, model: str) -> FactureExtraite: ...


class MockExtractor:
    """Extracteur de test : renvoie une facture par modèle, ou un défaut."""

    def __init__(self, par_modele=None, defaut=None):
        self.par_modele = par_modele or {}
        self.defaut = defaut
        self.appels = []

    def extraire(self, pdf: PdfDocument, model: str) -> FactureExtraite:
        self.appels.append((pdf.nom, model))
        if model in self.par_modele:
            return self.par_modele[model]
        if self.defaut is not None:
            return self.defaut
        raise KeyError(f"Aucune facture mock pour le modèle {model}")
