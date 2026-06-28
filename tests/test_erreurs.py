from app.main import _motif_erreur


def test_motif_cle_invalide():
    m = _motif_erreur(Exception("AuthenticationError: invalid x-api-key"))
    assert "Réglages" in m


def test_motif_quota():
    m = _motif_erreur(Exception("RateLimitError: 429 too many requests"))
    assert "crédits" in m or "quota" in m


def test_motif_generique_non_recursif():
    m = _motif_erreur(Exception("PDF corrompu"))
    assert m == "extraction impossible : PDF corrompu"
