from app.temps1.filtres import ligne_valide
from app.temps1.schemas import LigneFacture


def _ligne(**kw):
    base = dict(code="3400930000007", designation="X", prix_brut=6.0,
                remise_pct=10.0, prix_net=5.0, montant_ht=10.0)
    base.update(kw)
    return LigneFacture(**base)


def test_ligne_normale_retenue():
    assert ligne_valide(_ligne()) is True


def test_ug_net_zero_exclue():
    assert ligne_valide(_ligne(prix_net=0.0)) is False


def test_remise_100_exclue():
    assert ligne_valide(_ligne(remise_pct=100.0)) is False


def test_sans_code_exclue():
    assert ligne_valide(_ligne(code=None)) is False


def test_prix_brut_zero_exclu():
    assert ligne_valide(_ligne(prix_brut=0.0)) is False


def test_piege_1ug_dans_le_nom_reste_valide():
    # "+1UG" est un nom commercial, pas une unité gratuite : la ligne reste valide
    assert ligne_valide(_ligne(designation="FORCAPIL ANTI-CHUTE 2MOIS + 1UG")) is True
