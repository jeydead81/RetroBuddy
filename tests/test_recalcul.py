from app.db import get_connection, init_db
from app.temps4.recalcul import recalculer_prix_facture


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _doc(conn):
    cur = conn.execute(
        "INSERT INTO retro_documents (pharmacie_emettrice, pharmacie_destinataire, numero) "
        "VALUES ('A', 'B', 'N1')")
    conn.commit()
    return cur.lastrowid


def _ligne(conn, rid, prix_net, saisie_manuelle, code_resolu="C"):
    conn.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, code_resolu, qte, prix_net, "
        "bl_date, statut_ecart, saisie_manuelle, valide_utilisateur) "
        "VALUES (?, 'X', 'C', ?, 2, ?, '10/08/2025', 'resolu', ?, 0)",
        (rid, code_resolu, prix_net, saisie_manuelle))
    conn.commit()


def test_recalcul_tire_le_prix_du_referentiel(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    # Référentiel : prix corrigé à 9.0 pour le code C (date <= BL).
    conn.execute("INSERT INTO referentiel_prix (code, date_facture, prix_brut, remise_pct, prix_net) "
                 "VALUES ('C', '01/08/2025', 10.0, 10.0, 9.0)")
    conn.commit()
    _ligne(conn, rid, prix_net=5.0, saisie_manuelle=0)   # auto-rapprochée -> doit bouger
    _ligne(conn, rid, prix_net=7.0, saisie_manuelle=1)   # saisie main -> intacte

    res = recalculer_prix_facture(conn, rid)
    assert res["maj"] == 1
    assert res["eligibles"] == 1
    rows = conn.execute("SELECT prix_net, saisie_manuelle FROM retro_lignes ORDER BY id").fetchall()
    assert rows[0]["prix_net"] == 9.0
    assert rows[1]["prix_net"] == 7.0


def test_recalcul_sans_referentiel_ne_casse_rien(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    _ligne(conn, rid, prix_net=5.0, saisie_manuelle=0)   # aucun prix au référentiel
    res = recalculer_prix_facture(conn, rid)
    assert res["maj"] == 0
    row = conn.execute("SELECT prix_net FROM retro_lignes").fetchone()
    assert row["prix_net"] == 5.0                         # ligne laissée intacte
