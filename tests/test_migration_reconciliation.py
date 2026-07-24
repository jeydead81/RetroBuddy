from app.db import _soigner_reconciliations, get_connection, init_db


def _doc(conn, ok, motif, ta, tc):
    conn.execute(
        "INSERT INTO retro_documents (fichier, reconciliation_ok, motif_reconciliation, "
        "total_ht_affiche, total_ht_calcule) VALUES ('r.pdf', ?, ?, ?, ?)",
        (ok, motif, ta, tc))
    conn.commit()


def test_soigne_faux_positif_ancien_controle_ligne(tmp_path):
    c = get_connection(tmp_path / "t.db")
    init_db(c)
    _doc(c, 0, "qté ou prix net manquant pour le contrôle ligne", 1215.78, 1215.78)  # obsolète
    _doc(c, 0, "écart de total : 1100.0 calculé vs 1215.78 affiché", 1215.78, 1100.0)  # vrai écart
    _doc(c, 0, "écart TVA 20% : 100 vs 90 affiché", 1215.78, 1215.78)                 # motif actuel
    _soigner_reconciliations(c)
    c.commit()

    etats = [(r["reconciliation_ok"], r["motif_reconciliation"]) for r in c.execute(
        "SELECT reconciliation_ok, motif_reconciliation FROM retro_documents ORDER BY id")]
    assert etats[0] == (1, None)      # faux positif obsolète -> réparé
    assert etats[1][0] == 0           # vrai écart de total -> reste bloqué
    assert etats[2][0] == 0           # motif TVA actuel -> reste bloqué


def test_soin_ne_touche_pas_un_ecart_reel_meme_motif_manquant(tmp_path):
    # Sécurité : motif obsolète MAIS totaux qui ne réconcilient pas -> on ne répare pas.
    c = get_connection(tmp_path / "t.db")
    init_db(c)
    _doc(c, 0, "qté ou prix net manquant pour le contrôle ligne", 1215.78, 1200.0)
    _soigner_reconciliations(c)
    c.commit()
    assert c.execute("SELECT reconciliation_ok FROM retro_documents").fetchone()[0] == 0
