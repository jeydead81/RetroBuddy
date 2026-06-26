from app.codes.correspondance import resoudre_via_correspondance
from app.db import get_connection, init_db


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def test_resout_dans_les_deux_sens(tmp_path):
    conn = _conn(tmp_path)
    conn.execute("INSERT INTO correspondance_codes (code_a, code_b) VALUES (?, ?)",
                 ("3400930000007", "4006381333931"))
    conn.commit()
    assert resoudre_via_correspondance(conn, "3400930000007") == "4006381333931"
    assert resoudre_via_correspondance(conn, "4006381333931") == "3400930000007"


def test_inconnu_renvoie_none(tmp_path):
    conn = _conn(tmp_path)
    assert resoudre_via_correspondance(conn, "9999999999999") is None
    assert resoudre_via_correspondance(conn, None) is None
