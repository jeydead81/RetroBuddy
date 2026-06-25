from app.temps1.classifier import decision
from app.temps1.schemas import EnteteFacture, FactureExtraite


def _facture(type_document):
    return FactureExtraite(type_document=type_document, entete=EnteteFacture(), lignes=[])


def test_facture_marchandise_a_traiter():
    dec, motif = decision(_facture("facture_marchandise"))
    assert dec == "traiter"
    assert motif is None


def test_avoir_ignore():
    dec, motif = decision(_facture("avoir"))
    assert dec == "ignorer"
    assert "avoir" in motif.lower()


def test_abonnement_ignore():
    dec, _ = decision(_facture("abonnement_service"))
    assert dec == "ignorer"


def test_releve_ignore():
    dec, _ = decision(_facture("releve"))
    assert dec == "ignorer"


def test_type_inconnu_ignore():
    dec, motif = decision(_facture("grossiste"))
    assert dec == "ignorer"
    assert "grossiste" in motif
