from app.db import (_forcer_remises_positives, _soigner_reconciliations,
                    get_connection, init_db)


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


def test_force_remises_positives(tmp_path):
    c = get_connection(tmp_path / "t.db")
    init_db(c)
    c.execute("INSERT INTO retro_documents (id, fichier) VALUES (1, 'r.pdf')")
    c.execute("INSERT INTO factures (id, fichier) VALUES (1, 'f.pdf')")
    c.execute("INSERT INTO referentiel_prix (code, date_facture, remise_pct) "
              "VALUES ('X', '01/01/2025', -30.0)")
    c.execute("INSERT INTO retro_lignes (retro_id, designation, qte, remise_pct) "
              "VALUES (1, 'Y', 1, -15.0)")
    c.execute("INSERT INTO lignes_facture (facture_id, designation, remise_pct) "
              "VALUES (1, 'Z', 5.0)")                 # déjà positive -> inchangée
    c.commit()
    _forcer_remises_positives(c)
    c.commit()
    assert c.execute("SELECT remise_pct FROM referentiel_prix WHERE code='X'").fetchone()[0] == 30.0
    assert c.execute("SELECT remise_pct FROM retro_lignes WHERE designation='Y'").fetchone()[0] == 15.0
    assert c.execute("SELECT remise_pct FROM lignes_facture WHERE designation='Z'").fetchone()[0] == 5.0
