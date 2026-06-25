from app.temps1.extraction_ia import MockExtractor
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
