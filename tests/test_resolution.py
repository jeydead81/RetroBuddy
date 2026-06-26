from app.db import get_connection, init_db
from app.temps3.resolution import (
    accepter_orange, calcul_net, enregistrer_ligne, refuser_orange)


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    conn.execute("INSERT INTO retro_documents (id, fichier) VALUES (1, 'test.pdf')")
    conn.commit()
    return conn


def _ligne(conn, **kw):
    base = dict(retro_id=1, designation="X", qte=2.0, statut_ecart="rouge",
                valide_utilisateur=0, saisie_manuelle=0)
    base.update(kw)
    cols = ", ".join(base)
    ph = ", ".join("?" for _ in base)
    cur = conn.execute(f"INSERT INTO retro_lignes ({cols}) VALUES ({ph})", tuple(base.values()))
    conn.commit()
    return cur.lastrowid


def test_calcul_net_sans_ug():
    assert calcul_net(qte=2, prix_brut=10.0, remise_pct=20.0, ug=0) == 8.0


def test_calcul_net_avec_ug():
    assert calcul_net(qte=2, prix_brut=10.0, remise_pct=20.0, ug=2) == 4.0


def test_enregistrer_ligne_recalcule_et_valide(tmp_path):
    conn = _conn(tmp_path)
    lid = _ligne(conn)
    r = enregistrer_ligne(conn, lid, prix_brut=10.0, remise_pct=20.0, ug=0)
    assert r["prix_net"] == 8.0
    row = conn.execute("SELECT prix_net, statut_ecart, valide_utilisateur, saisie_manuelle "
                       "FROM retro_lignes WHERE id=?", (lid,)).fetchone()
    assert row["prix_net"] == 8.0
    assert row["valide_utilisateur"] == 1
    assert row["saisie_manuelle"] == 1
    assert row["statut_ecart"] == "resolu"


def test_accepter_orange(tmp_path):
    conn = _conn(tmp_path)
    lid = _ligne(conn, statut_ecart="orange", prix_net=4.5, code_resolu="C")
    accepter_orange(conn, lid)
    row = conn.execute("SELECT statut_ecart, valide_utilisateur FROM retro_lignes WHERE id=?",
                       (lid,)).fetchone()
    assert row["statut_ecart"] == "resolu"
    assert row["valide_utilisateur"] == 1


def test_refuser_orange_repasse_rouge(tmp_path):
    conn = _conn(tmp_path)
    lid = _ligne(conn, statut_ecart="orange", prix_net=4.5, code_resolu="C")
    refuser_orange(conn, lid)
    row = conn.execute("SELECT statut_ecart, valide_utilisateur, prix_net, code_resolu "
                       "FROM retro_lignes WHERE id=?", (lid,)).fetchone()
    assert row["statut_ecart"] == "rouge"
    assert row["valide_utilisateur"] == 0
    assert row["prix_net"] is None
    assert row["code_resolu"] is None
