from app.codes.checksum import cip13_valide, ean13_valide, normaliser_code, type_de_code


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


def test_gtin14_zero_de_tete_est_un_ean13():
    # Facture Bayer : code sorti avec le 0 de tête (GTIN-14) -> EAN13 réel.
    assert type_de_code("03401396868613") == "EAN13"
    assert normaliser_code("03401396868613") == "3401396868613"
    assert normaliser_code(" 3400930000007 ") == "3400930000007"   # espaces retirés
    assert normaliser_code("82803476") == "82803476"               # interne inchangé
    assert normaliser_code(None) == ""
