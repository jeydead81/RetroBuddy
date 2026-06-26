from app.db import get_connection, init_db
from app.temps2.matching import resoudre_par_designation


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code, designation):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_net, designation) "
        "VALUES (?, ?, ?, ?)",
        (code, "2025-08-01", 5.0, designation))
    conn.commit()


def test_candidat_par_designation_proche(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930156421", "REXORUBIA GLE 350G")
    code, desig, score = resoudre_par_designation(conn, "REXORUBIA GLE 350 G", 0.80)
    assert code == "3400930156421"
    assert desig == "REXORUBIA GLE 350G"
    assert score >= 0.95


def test_aucun_candidat_sous_le_seuil(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930156421", "REXORUBIA GLE 350G")
    code, desig, score = resoudre_par_designation(conn, "DOLIPRANE 1000MG", 0.80)
    assert code is None
    assert desig is None


def test_meilleur_candidat(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "A", "ANTHELIOS 50 AGE CORRECT AVEC PARFUM")
    _ref(conn, "B", "DOLIPRANE 1000MG")
    code, desig, score = resoudre_par_designation(conn, "ANTHELIOS 50 AGE CORRECT", 0.70)
    assert code == "A"
