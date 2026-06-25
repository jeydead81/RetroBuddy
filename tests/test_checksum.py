from app.codes.checksum import cip13_valide, ean13_valide, type_de_code


def test_cip13_valide():
    assert cip13_valide("3400930000007") is True


def test_cip13_mauvaise_cle():
    assert cip13_valide("3400930000000") is False


def test_cip13_sans_prefixe_34009():
    # EAN13 valide mais pas un CIP (mauvais préfixe)
    assert cip13_valide("4006381333931") is False


def test_ean13_valide():
    assert ean13_valide("4006381333931") is True


def test_type_de_code():
    assert type_de_code("3400930000007") == "CIP13"
    assert type_de_code("4006381333931") == "EAN13"
    assert type_de_code("20007519") == "interne"   # code interne court (AbbVie)
    assert type_de_code("107621") == "interne"      # code interne court (Fresenius)
    assert type_de_code("3400930000000") == "inconnu"  # 13 chiffres, clé KO
    assert type_de_code(None) == "inconnu"
