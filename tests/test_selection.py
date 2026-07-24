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


def test_cip_dans_code_interne_repris_comme_code():
    # Cas Bayer : article interne dans `code`, vrai CIP/EAN dans `code_interne`
    # -> on prend le CIP/EAN (sinon la rétro ne le retrouve pas).
    q = qualifier_ligne(_ligne(code="82803476", code_interne="3400930000007"))
    assert q.inclure is True
    assert q.code_ref == "3400930000007"
    assert q.type_code == "CIP13"


def test_gtin14_zero_de_tete_normalise_en_ean13():
    # Cas Bayer réel : le modèle sort le CIP dans `code` mais en 14 chiffres
    # (0 + EAN13). Il faut le stocker en 13 chiffres pour matcher la rétro.
    q = qualifier_ligne(_ligne(code="03401396868613", code_interne="82803476"))
    assert q.inclure is True
    assert q.code_ref == "3401396868613"
    assert q.type_code == "EAN13"


def test_cip_dans_code_prioritaire_sur_interne():
    # Si le CIP est bien dans `code`, un code_interne présent ne le détrône pas.
    q = qualifier_ligne(_ligne(code="3400930000007", code_interne="82803476"))
    assert q.code_ref == "3400930000007"
    assert q.type_code == "CIP13"


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
