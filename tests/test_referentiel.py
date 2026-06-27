from app.db import get_connection, init_db
from app.temps1.referentiel import enregistrer_referentiel
from app.temps1.schemas import LigneFacture


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ligne(net):
    return LigneFacture(designation="X", prix_brut=6.0, remise_pct=10.0,
                        prix_net=net, montant_ht=net)


def test_historisation_deux_dates(tmp_path):
    conn = _conn(tmp_path)
    enregistrer_referentiel(conn, 1, "2026-01-10", "URGO",
                            [("3400930000007", "CIP13", _ligne(5.0))])
    enregistrer_referentiel(conn, 2, "2026-02-10", "URGO",
                            [("3400930000007", "CIP13", _ligne(4.5))])
    rows = conn.execute(
        "SELECT date_facture, prix_net FROM referentiel_prix WHERE code=? ORDER BY date_facture",
        ("3400930000007",),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["prix_net"] == 5.0
    assert rows[1]["prix_net"] == 4.5


def test_idempotence_meme_code_meme_date(tmp_path):
    conn = _conn(tmp_path)
    enregistrer_referentiel(conn, 1, "2026-01-10", "URGO",
                            [("3400930000007", "CIP13", _ligne(5.0))])
    enregistrer_referentiel(conn, 9, "2026-01-10", "URGO",
                            [("3400930000007", "CIP13", _ligne(4.0))])
    rows = conn.execute(
        "SELECT prix_net, facture_id FROM referentiel_prix WHERE code=?",
        ("3400930000007",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["prix_net"] == 4.0      # remplacé par la dernière ingestion
    assert rows[0]["facture_id"] == 9


def test_reingestion_met_a_jour_meme_apres_edition_manuelle(tmp_path):
    conn = _conn(tmp_path)
    enregistrer_referentiel(conn, 1, "2026-01-10", "URGO",
                            [("3400930000007", "CIP13", _ligne(5.0))])
    # Correction manuelle (marquée modifie_manuellement=1)...
    conn.execute("UPDATE referentiel_prix SET prix_net=42.0, modifie_manuellement=1 "
                 "WHERE code='3400930000007' AND date_facture='2026-01-10'")
    conn.commit()
    # ... mais une ré-ingestion de la même facture met bien le prix à jour
    # (les prix bougent au fil de l'année : la dernière ingestion fait foi).
    enregistrer_referentiel(conn, 7, "2026-01-10", "URGO",
                            [("3400930000007", "CIP13", _ligne(4.0))])
    r = conn.execute("SELECT prix_net, facture_id, modifie_manuellement FROM referentiel_prix "
                     "WHERE code='3400930000007'").fetchone()
    assert r["prix_net"] == 4.0                 # le nouveau prix s'applique
    assert r["facture_id"] == 7
    assert r["modifie_manuellement"] == 0       # redevient une valeur « facture »


def test_stocke_type_code_et_labo(tmp_path):
    conn = _conn(tmp_path)
    enregistrer_referentiel(conn, 3, "2026-03-02", "ABBVIE",
                            [("20007519", "interne", _ligne(4685.34))])
    r = conn.execute("SELECT code, type_code, labo FROM referentiel_prix").fetchone()
    assert r["code"] == "20007519"
    assert r["type_code"] == "interne"
    assert r["labo"] == "ABBVIE"
