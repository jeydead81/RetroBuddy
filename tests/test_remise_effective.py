from app.db import get_connection, init_db
from app.temps4.facture_builder import _remise_effective, construire_facture


def test_remise_effective_formule():
    assert _remise_effective(8.23, 6.16) == 25.15      # cascade Bayer 4 % + 22 %
    assert _remise_effective(10.0, 9.0) == 10.0
    assert _remise_effective(None, 5.0) is None        # brut absent
    assert _remise_effective(0.0, 5.0) is None         # brut nul
    assert _remise_effective(8.0, None) is None        # net absent


def _conn(tmp_path):
    c = get_connection(tmp_path / "t.db")
    init_db(c)
    c.execute("INSERT INTO retro_documents (id, fichier, numero) VALUES (1, 'r.pdf', 'F1')")
    return c


def test_remise_cascade_forcee_sur_facture(tmp_path):
    c = _conn(tmp_path)
    # remise_pct NULL (cascade) mais brut + net présents
    c.execute("INSERT INTO retro_lignes (retro_id, designation, qte, prix_brut, prix_net, "
              "tva, statut_ecart, bl_numero, bl_date) VALUES "
              "(1, 'Hydralin', 12, 8.23, 6.16, 10.0, 'resolu', 'BL1', '01/03/2025')")
    c.commit()
    f = construire_facture(c, 1)
    ligne = f.groupes[0].lignes[0]
    assert ligne.remise_pct == 25.15                   # calculée et affichée


def test_remise_simple_conservee(tmp_path):
    c = _conn(tmp_path)
    c.execute("INSERT INTO retro_lignes (retro_id, designation, qte, prix_brut, remise_pct, "
              "prix_net, tva, statut_ecart, bl_numero, bl_date) VALUES "
              "(1, 'X', 1, 10.0, 30.0, 7.0, 20.0, 'resolu', 'BL1', '01/03/2025')")
    c.commit()
    f = construire_facture(c, 1)
    assert f.groupes[0].lignes[0].remise_pct == 30.0   # remise affichée -> inchangée
