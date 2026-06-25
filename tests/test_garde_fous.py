from app.temps1.garde_fous import checksum_ok, reconcilier_totaux
from app.temps1.schemas import LigneFacture


def _ligne(code, montant):
    return LigneFacture(code=code, designation="X", prix_brut=6.0, remise_pct=10.0,
                        prix_net=5.0, montant_ht=montant)


def test_checksum_ok_vrai_code():
    assert checksum_ok(_ligne("3400930000007", 10.0)) is True


def test_checksum_ok_code_invalide():
    assert checksum_ok(_ligne("3400930000000", 10.0)) is False


def test_reconciliation_dans_tolerance():
    lignes = [_ligne("3400930000007", 10.0), _ligne("4006381333931", 5.0)]
    ok, total = reconcilier_totaux(lignes, total_affiche=15.0, seuil_pct=1.0)
    assert ok is True
    assert total == 15.0


def test_reconciliation_hors_tolerance():
    lignes = [_ligne("3400930000007", 10.0)]
    ok, total = reconcilier_totaux(lignes, total_affiche=20.0, seuil_pct=1.0)
    assert ok is False
    assert total == 10.0


def test_reconciliation_total_absent():
    lignes = [_ligne("3400930000007", 10.0)]
    ok, total = reconcilier_totaux(lignes, total_affiche=None, seuil_pct=1.0)
    assert ok is False
