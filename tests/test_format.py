from app.format_util import fmt_qte


def test_fmt_qte_entier():
    assert fmt_qte(3.0) == "3"
    assert fmt_qte(1) == "1"
    assert fmt_qte(12) == "12"


def test_fmt_qte_fraction_conservee():
    assert fmt_qte(2.5) == "2.5"


def test_fmt_qte_vide():
    assert fmt_qte(None) == ""
