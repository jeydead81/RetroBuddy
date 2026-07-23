from app.db import get_connection, init_db
from app.temps2.calcul_prix import prix_a_date


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code, date_facture, prix_net):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_brut, remise_pct, prix_net) "
        "VALUES (?, ?, ?, ?, ?)",
        (code, date_facture, prix_net + 1, 10.0, prix_net))
    conn.commit()


def test_dernier_prix_avant_date_bl(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "01/07/2025", 5.0)
    _ref(conn, "C", "05/08/2025", 4.5)
    r = prix_a_date(conn, "C", "10/08/2025")   # les deux <= BL, on prend le + récent
    assert r["prix_net"] == 4.5


def test_prix_anterieur_prioritaire_sur_posterieur(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "01/07/2025", 5.0)
    _ref(conn, "C", "05/08/2025", 4.5)
    r = prix_a_date(conn, "C", "15/07/2025")   # un antérieur existe -> il gagne
    assert r["prix_net"] == 5.0


def test_repli_prix_posterieur_dans_la_fenetre(tmp_path):
    # Cas MIGHTY PATCH : BL 08/09, seul prix au réf. daté 06/10 (28 j après).
    # Mieux vaut ce prix proche qu'une ligne en anomalie.
    conn = _conn(tmp_path)
    _ref(conn, "C", "06/10/2025", 5.10)
    r = prix_a_date(conn, "C", "08/09/2025")
    assert r is not None
    assert r["prix_net"] == 5.10


def test_repli_prend_le_posterieur_le_plus_proche(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "20/09/2025", 4.8)   # +12 j
    _ref(conn, "C", "20/10/2025", 4.2)   # +42 j
    r = prix_a_date(conn, "C", "08/09/2025")
    assert r["prix_net"] == 4.8          # le plus proche du BL


def test_posterieur_au_dela_de_2_mois_refuse(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "05/08/2025", 4.5)   # 65 j après le BL -> hors fenêtre
    assert prix_a_date(conn, "C", "01/06/2025") is None


def test_bl_date_illisible(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "05/08/2025", 4.5)
    assert prix_a_date(conn, "C", "le 5 août") is None
