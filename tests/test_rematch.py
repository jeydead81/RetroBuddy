from app.db import get_connection, init_db
from app.temps3.rematch import rematcher

CFG = {"seuil_match_bas": 0.80, "seuil_match_auto": 0.95}


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _retro_doc(conn):
    cur = conn.execute("INSERT INTO retro_documents (fichier) VALUES ('r.pdf')")
    return cur.lastrowid


def _ligne_rouge(conn, retro_id, code, designation, bl_date="10/08/2025"):
    conn.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, qte, tva, bl_numero, bl_date, "
        "statut_ecart, valide_utilisateur, saisie_manuelle) "
        "VALUES (?, ?, ?, 1, 10.0, 'BL1', ?, 'rouge', 0, 0)",
        (retro_id, designation, code, bl_date))
    conn.commit()


def test_rematch_passe_rouge_en_resolu_apres_ajout_referentiel(tmp_path):
    conn = _conn(tmp_path)
    rid = _retro_doc(conn)
    _ligne_rouge(conn, rid, "3400937882248", "IMODIUMDUO CPR 12")
    assert rematcher(conn, CFG)["resolu"] == 0
    conn.execute("INSERT INTO referentiel_prix (code, date_facture, prix_brut, remise_pct, "
                 "prix_net, designation) VALUES ('3400937882248', '01/08/2025', 3.0, 10.0, 2.7, "
                 "'IMODIUMDUO CPR 12')")
    conn.commit()
    compteurs = rematcher(conn, CFG)
    assert compteurs["resolu"] == 1
    r = conn.execute("SELECT statut_ecart, prix_net FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "resolu"
    assert r["prix_net"] == 2.7


def test_rematch_epargne_les_lignes_saisies(tmp_path):
    conn = _conn(tmp_path)
    rid = _retro_doc(conn)
    conn.execute("INSERT INTO retro_lignes (retro_id, designation, code, qte, tva, bl_numero, "
                 "bl_date, prix_net, statut_ecart, valide_utilisateur, saisie_manuelle) "
                 "VALUES (?, 'X', '3400937882248', 1, 10.0, 'BL1', '10/08/2025', 9.9, 'rouge', 0, 1)",
                 (rid,))
    conn.execute("INSERT INTO referentiel_prix (code, date_facture, prix_net, designation) "
                 "VALUES ('3400937882248', '01/08/2025', 2.7, 'X')")
    conn.commit()
    rematcher(conn, CFG)
    assert conn.execute("SELECT prix_net FROM retro_lignes").fetchone()["prix_net"] == 9.9
