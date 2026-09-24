"""Lien « facture labo source » sur chaque ligne de la facture rétro (étape 4)."""
from app.db import get_connection, init_db
from app.temps4.facture_builder import construire_facture

CODE = "3400930000001"


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _labo(conn, date="15/07/2025", net=9.0, source="facture", avec_facture=True):
    fid = None
    if avec_facture:
        fid = conn.execute(
            "INSERT INTO factures (labo, numero_facture, date_facture, statut) "
            "VALUES ('BIOGARAN', 'F42', ?, 'ingeree')", (date,)).lastrowid
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, labo, prix_brut, remise_pct, "
        "prix_net, designation, facture_id, source) VALUES (?, ?, 'BIOGARAN', 10.0, 10.0, ?, "
        "'DOLIPRANE', ?, ?)", (CODE, date, net, fid, source))
    conn.commit()
    return fid


def _retro(conn, net=9.0, saisie=0, code_resolu=CODE):
    rid = conn.execute(
        "INSERT INTO retro_documents (pharmacie_emettrice, numero, date_vente) "
        "VALUES ('SERALY', 'N1', '22/09/2025')").lastrowid
    conn.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, code_resolu, qte, prix_brut, "
        "remise_pct, prix_net, tva, bl_numero, bl_date, statut_ecart, saisie_manuelle) "
        "VALUES (?, 'DOLIPRANE', ?, ?, 2, 10.0, 10.0, ?, 2.1, 'BL1', '01/08/2025', 'resolu', ?)",
        (rid, CODE, code_resolu, net, saisie))
    conn.commit()
    return rid


def _ligne(f):
    return f.groupes[0].lignes[0]


def test_lien_vers_facture_labo_source(tmp_path):
    conn = _conn(tmp_path)
    fid = _labo(conn)
    l = _ligne(construire_facture(conn, _retro(conn)))
    assert l.source_facture_id == fid
    assert l.source_labo == "BIOGARAN"
    assert l.source_date == "15/07/2025"
    assert l.source_code == CODE


def test_pas_de_lien_si_saisie_manuelle(tmp_path):
    conn = _conn(tmp_path)
    _labo(conn)
    assert _ligne(construire_facture(conn, _retro(conn, saisie=1))).source_facture_id is None


def test_pas_de_lien_si_prix_de_resolution(tmp_path):
    conn = _conn(tmp_path)
    _labo(conn, source="resolution", avec_facture=False)
    assert _ligne(construire_facture(conn, _retro(conn))).source_facture_id is None


def test_pas_de_lien_si_facture_labo_supprimee(tmp_path):
    conn = _conn(tmp_path)
    fid = _labo(conn)
    conn.execute("DELETE FROM factures WHERE id=?", (fid,))
    conn.commit()
    assert _ligne(construire_facture(conn, _retro(conn))).source_facture_id is None


def test_pas_de_lien_si_prix_ne_correspond_plus(tmp_path):
    conn = _conn(tmp_path)
    _labo(conn, net=9.0)
    assert _ligne(construire_facture(conn, _retro(conn, net=8.5))).source_facture_id is None


def test_pas_de_lien_si_referentiel_modifie_a_la_main(tmp_path):
    conn = _conn(tmp_path)
    _labo(conn)
    conn.execute("UPDATE referentiel_prix SET modifie_manuellement=1")
    conn.commit()
    assert _ligne(construire_facture(conn, _retro(conn))).source_facture_id is None


def test_pas_de_lien_sans_code_resolu(tmp_path):
    conn = _conn(tmp_path)
    _labo(conn)
    assert _ligne(construire_facture(conn, _retro(conn, code_resolu=None))).source_facture_id is None
