from app.temps1.filtres import est_ligne_prix
from app.temps1.schemas import LigneFacture


def _ligne(**kw):
    base = dict(code="3400930000007", designation="X", prix_brut=6.0,
                remise_pct=10.0, prix_net=5.0, montant_ht=10.0)
    base.update(kw)
    return LigneFacture(**base)


def test_ligne_prix_normale():
    assert est_ligne_prix(_ligne()) is True


def test_ug_net_zero_exclue():
    assert est_ligne_prix(_ligne(prix_net=0.0)) is False


def test_remise_100_exclue():
    assert est_ligne_prix(_ligne(remise_pct=100.0)) is False


def test_prix_brut_zero_exclu():
    assert est_ligne_prix(_ligne(prix_brut=0.0)) is False


def test_sans_code_reste_une_ligne_prix():
    # Le rattachement à un identifiant n'est plus jugé ici (cf. selection) :
    # une ligne sans CIP peut être une vraie ligne de prix.
    assert est_ligne_prix(_ligne(code=None)) is True


def test_piege_1ug_dans_le_nom_reste_ligne_prix():
    assert est_ligne_prix(_ligne(designation="FORCAPIL ANTI-CHUTE 2MOIS + 1UG")) is True
