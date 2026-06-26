from pathlib import Path
from typing import Protocol

import anthropic

from app.temps1.cout import cout_appel
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


class ExtractionError(RuntimeError):
    pass


class ClaudeExtractor:
    """Extracteur réel : envoie le PDF à Claude (lecture native) avec sortie structurée."""

    def __init__(self, api_key: str, prompt_path="prompts/extraction_facture.txt",
                 output_format=FactureExtraite):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._prompt = Path(prompt_path).read_text(encoding="utf-8")
        self._output_format = output_format
        self.dernier_cout = 0.0
        self.cout_cumule = 0.0

    def extraire(self, pdf: PdfDocument, model: str):
        resp = self._client.messages.parse(
            model=model,
            max_tokens=16000,
            system=[{"type": "text", "text": self._prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document",
                     "source": {"type": "base64", "media_type": "application/pdf",
                                "data": pdf.base64}},
                    {"type": "text", "text": "Extrais cette facture selon le schéma."},
                ],
            }],
            output_format=self._output_format,
        )
        self.dernier_cout = cout_appel(model, resp.usage)
        self.cout_cumule += self.dernier_cout
        if resp.stop_reason == "refusal":
            raise ExtractionError("extraction refusée par le modèle")
        if resp.parsed_output is None:
            raise ExtractionError("extraction non conforme au schéma")
        return resp.parsed_output
