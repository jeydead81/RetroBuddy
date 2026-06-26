from app.temps1.schemas import LigneFacture
from app.temps1.selection import qualifier_ligne


def _ligne(**kw):
    base = dict(designation="X", prix_brut=6.0, remise_pct=10.0,
                prix_net=5.0, montant_ht=10.0)
    base.update(kw)
    return LigneFacture(**base)


def test_cip13_incluse():
    q = qualifier_ligne(_ligne(code="3400930000007"))
    assert q.inclure is True
    assert q.code_ref == "3400930000007"
    assert q.type_code == "CIP13"


def test_ean13_incluse():
    q = qualifier_ligne(_ligne(code="4006381333931"))
    assert q.inclure is True
    assert q.type_code == "EAN13"


def test_sans_cip_mais_code_interne_incluse():
    q = qualifier_ligne(_ligne(code=None, code_interne="20007519"))
    assert q.inclure is True
    assert q.code_ref == "20007519"
    assert q.type_code == "interne"
    assert "CIP" in q.note


def test_code_interne_dans_le_champ_code_incluse():
    # Le modèle peut mettre le code interne dans `code` plutôt que `code_interne`.
    q = qualifier_ligne(_ligne(code="20007519"))
    assert q.inclure is True
    assert q.code_ref == "20007519"
    assert q.type_code == "interne"


def test_code_13_invalide_exclue():
    q = qualifier_ligne(_ligne(code="3400930000000"))
    assert q.inclure is False
    assert q.type_code == "inconnu"


def test_non_prix_exclue():
    q = qualifier_ligne(_ligne(code="3400930000007", prix_net=0.0))
    assert q.inclure is False


def test_aucun_identifiant_exclue():
    q = qualifier_ligne(_ligne(code=None, code_interne=None))
    assert q.inclure is False
