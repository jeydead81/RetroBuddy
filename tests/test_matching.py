from app.db import get_connection, init_db
from app.temps2.matching import resoudre_code


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_net) VALUES (?, ?, ?)",
        (code, "2025-08-01", 5.0))
    conn.commit()


def test_passe1_code_identique(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007")
    assert resoudre_code(conn, "3400930000007") == ("3400930000007", 1)


def test_passe2_pont_cip_ean(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "4006381333931")  # le référentiel a l'EAN
    conn.execute("INSERT INTO correspondance_codes (code_a, code_b) VALUES (?, ?)",
                 ("3400930000007", "4006381333931"))
    conn.commit()
    # la ligne LGO porte le CIP -> résolu via le pont vers l'EAN présent
    assert resoudre_code(conn, "3400930000007") == ("4006381333931", 2)


def test_introuvable(tmp_path):
    conn = _conn(tmp_path)
    assert resoudre_code(conn, "3400930000007") == (None, None)
