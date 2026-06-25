from app.db import get_connection, init_db


def _tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r["name"] for r in rows}


def test_init_db_cree_les_tables(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    noms = _tables(conn)
    assert {"factures", "lignes_facture", "referentiel_prix", "abreviations_labo"} <= noms


def test_init_db_idempotent(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    init_db(conn)  # ne doit pas lever
    assert "referentiel_prix" in _tables(conn)
