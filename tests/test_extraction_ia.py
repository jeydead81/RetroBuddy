import types

import pytest

from app.temps1.extraction_ia import ClaudeExtractor, ExtractionError, MockExtractor
from app.temps1.pdf_reader import PdfDocument
from app.temps1.schemas import EnteteFacture, FactureExtraite


def _pdf():
    return PdfDocument(nom="f.pdf", base64="", taille_octets=0)


def _facture(t):
    return FactureExtraite(type_document=t, entete=EnteteFacture(), lignes=[])


def test_mock_retourne_le_defaut():
    f = _facture("facture_marchandise")
    ex = MockExtractor(defaut=f)
    assert ex.extraire(_pdf(), "claude-sonnet-4-6") is f


def test_mock_retourne_par_modele_et_trace_les_appels():
    fs = _facture("facture_marchandise")
    fo = _facture("avoir")
    ex = MockExtractor(par_modele={"claude-sonnet-4-6": fs, "claude-opus-4-8": fo})
    assert ex.extraire(_pdf(), "claude-sonnet-4-6") is fs
    assert ex.extraire(_pdf(), "claude-opus-4-8") is fo
    assert ex.appels == [("f.pdf", "claude-sonnet-4-6"), ("f.pdf", "claude-opus-4-8")]


# --- ClaudeExtractor : garde-fous sur le stop_reason (client factice, pas de réseau) ---

def _usage():
    return types.SimpleNamespace(input_tokens=10, output_tokens=10,
                                 cache_read_input_tokens=0, cache_creation_input_tokens=0)


class _FakeResp:
    def __init__(self, stop_reason, parsed=None):
        self.stop_reason = stop_reason
        self.parsed_output = parsed
        self.usage = _usage()


def _ext(resp):
    ext = ClaudeExtractor(api_key="test")          # pas d'appel réseau à la construction
    ext._client = types.SimpleNamespace(
        messages=types.SimpleNamespace(parse=lambda **kw: resp))
    return ext


def test_troncature_leve_erreur():
    with pytest.raises(ExtractionError, match="tronqu"):
        _ext(_FakeResp("max_tokens")).extraire(_pdf(), "claude-sonnet-4-6")


def test_refus_leve_erreur():
    with pytest.raises(ExtractionError):
        _ext(_FakeResp("refusal")).extraire(_pdf(), "claude-sonnet-4-6")


def test_extraction_ok_renvoie_le_parsed():
    f = _facture("facture_marchandise")
    assert _ext(_FakeResp("end_turn", parsed=f)).extraire(_pdf(), "claude-sonnet-4-6") is f
