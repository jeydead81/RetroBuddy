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


def test_ignore_les_prix_posterieurs_au_bl(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "01/07/2025", 5.0)
    _ref(conn, "C", "05/08/2025", 4.5)
    r = prix_a_date(conn, "C", "15/07/2025")   # seul le 01/07 <= BL
    assert r["prix_net"] == 5.0


def test_aucun_prix_avant_le_bl(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "05/08/2025", 4.5)
    assert prix_a_date(conn, "C", "01/06/2025") is None


def test_bl_date_illisible(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "05/08/2025", 4.5)
    assert prix_a_date(conn, "C", "le 5 août") is None
