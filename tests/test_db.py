import sqlite3

from app.db import get_connection, init_db


def _tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r["name"] for r in rows}


def _colonnes(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


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


def test_schema_neuf_contient_les_nouvelles_colonnes(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    assert {"type_code", "labo"} <= _colonnes(conn, "referentiel_prix")
    assert "motif_ligne" in _colonnes(conn, "lignes_facture")
    assert "cout_estime" in _colonnes(conn, "factures")


def test_migration_ajoute_colonnes_a_une_base_ancienne(tmp_path):
    # Base « ancienne » : schéma V1 sans les colonnes ajoutées ensuite.
    p = tmp_path / "old.db"
    c0 = sqlite3.connect(p)
    c0.executescript(
        "CREATE TABLE factures (id INTEGER PRIMARY KEY, fichier TEXT);"
        "CREATE TABLE referentiel_prix (code TEXT, date_facture TEXT, prix_net REAL,"
        " PRIMARY KEY(code, date_facture));"
        "CREATE TABLE lignes_facture (id INTEGER PRIMARY KEY, code TEXT, valide INTEGER);"
    )
    c0.commit()
    c0.close()

    conn = get_connection(p)
    init_db(conn)  # doit migrer sans perdre les tables existantes
    assert {"type_code", "labo"} <= _colonnes(conn, "referentiel_prix")
    assert "motif_ligne" in _colonnes(conn, "lignes_facture")
    assert "cout_estime" in _colonnes(conn, "factures")


def test_init_db_cree_les_tables_temps2(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    noms = _tables(conn)
    assert {"retro_documents", "retro_lignes", "correspondance_codes"} <= noms
