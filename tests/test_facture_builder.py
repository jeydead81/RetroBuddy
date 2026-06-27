from app.db import get_connection, init_db
from app.temps4.facture_builder import construire_facture


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _doc(conn):
    cur = conn.execute(
        "INSERT INTO retro_documents (pharmacie_emettrice, pharmacie_destinataire, "
        "numero, date_vente) VALUES ('SERALY', 'CENON', 'N1', '22/09/2025')")
    return cur.lastrowid


def _ligne(conn, retro_id, designation, qte, prix_net, tva, bl_numero, bl_date,
           statut="resolu"):
    conn.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, qte, prix_brut, remise_pct, "
        "prix_net, tva, bl_numero, bl_date, statut_ecart) "
        "VALUES (?, ?, 'C', ?, ?, 10.0, ?, ?, ?, ?, ?)",
        (retro_id, designation, qte, (prix_net + 1), prix_net, tva, bl_numero, bl_date, statut))
    conn.commit()


def test_regroupement_par_bl_et_montant_ht(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    _ligne(conn, rid, "A", 2, 5.0, 10.0, "BL1", "01/08/2025")
    _ligne(conn, rid, "B", 1, 4.0, 10.0, "BL1", "01/08/2025")
    _ligne(conn, rid, "C", 3, 2.0, 20.0, "BL2", "04/08/2025")
    f = construire_facture(conn, rid)
    assert f.emettrice == "SERALY"
    assert len(f.groupes) == 2
    assert f.groupes[0].bl_numero == "BL1"
    assert len(f.groupes[0].lignes) == 2
    assert f.groupes[0].lignes[0].montant_ht == 10.0
    assert f.groupes[1].lignes[0].montant_ht == 6.0


def test_ventilation_tva_et_totaux(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    _ligne(conn, rid, "A", 2, 5.0, 10.0, "BL1", "01/08/2025")
    _ligne(conn, rid, "C", 3, 2.0, 20.0, "BL2", "04/08/2025")
    f = construire_facture(conn, rid)
    assert f.total_ht == 16.0
    taux = {v.taux: v for v in f.ventilation}
    assert taux[10.0].base_ht == 10.0
    assert taux[10.0].montant_tva == 1.0
    assert taux[20.0].montant_tva == 1.2
    assert f.total_tva == 2.2
    assert f.total_ttc == 18.2


def test_exclut_les_rouges_et_bloque(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    _ligne(conn, rid, "A", 2, 5.0, 10.0, "BL1", "01/08/2025", statut="resolu")
    conn.execute("INSERT INTO retro_lignes (retro_id, designation, qte, tva, bl_numero, "
                 "bl_date, statut_ecart) VALUES (?, 'ROUGE', 1, 10.0, 'BL1', '01/08/2025', 'rouge')",
                 (rid,))
    conn.commit()
    f = construire_facture(conn, rid)
    assert f.bloquee is True
    assert f.n_rouge == 1
    designations = [l.designation for g in f.groupes for l in g.lignes]
    assert designations == ["A"]


def test_non_bloquee_si_tout_resolu(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    _ligne(conn, rid, "A", 2, 5.0, 10.0, "BL1", "01/08/2025")
    f = construire_facture(conn, rid)
    assert f.bloquee is False
    assert f.n_rouge == 0


def test_retro_id_inconnu_renvoie_none(tmp_path):
    assert construire_facture(_conn(tmp_path), 999) is None
