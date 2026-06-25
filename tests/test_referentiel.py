from app.db import get_connection, init_db
from app.temps1.referentiel import enregistrer_lignes_referentiel
from app.temps1.schemas import LigneFacture


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ligne(code, net):
    return LigneFacture(code=code, designation="X", prix_brut=6.0, remise_pct=10.0,
                        prix_net=net, montant_ht=net)


def test_historisation_deux_dates(tmp_path):
    conn = _conn(tmp_path)
    enregistrer_lignes_referentiel(conn, 1, "2026-01-10", [_ligne("3400930000007", 5.0)])
    enregistrer_lignes_referentiel(conn, 2, "2026-02-10", [_ligne("3400930000007", 4.5)])
    rows = conn.execute(
        "SELECT date_facture, prix_net FROM referentiel_prix WHERE code=? ORDER BY date_facture",
        ("3400930000007",),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["prix_net"] == 5.0
    assert rows[1]["prix_net"] == 4.5


def test_idempotence_meme_code_meme_date(tmp_path):
    conn = _conn(tmp_path)
    enregistrer_lignes_referentiel(conn, 1, "2026-01-10", [_ligne("3400930000007", 5.0)])
    enregistrer_lignes_referentiel(conn, 9, "2026-01-10", [_ligne("3400930000007", 4.0)])
    rows = conn.execute(
        "SELECT prix_net, facture_id FROM referentiel_prix WHERE code=?",
        ("3400930000007",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["prix_net"] == 4.0      # remplacé par la dernière ingestion
    assert rows[0]["facture_id"] == 9
