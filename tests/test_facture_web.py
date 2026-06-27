from fastapi.testclient import TestClient

from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _doc(client):
    from app.db import get_connection
    conn = get_connection(client.app.state.db_path)
    cur = conn.execute(
        "INSERT INTO retro_documents (pharmacie_emettrice, pharmacie_destinataire, numero) "
        "VALUES ('SERALY', 'CENON', 'N1')")
    rid = cur.lastrowid
    conn.commit()
    return conn, rid


def _ligne(conn, rid, statut="resolu", prix_net=5.0):
    conn.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, qte, prix_brut, remise_pct, "
        "prix_net, tva, bl_numero, bl_date, statut_ecart) "
        "VALUES (?, 'PRODUIT A', 'C', 2, 6.0, 10.0, ?, 10.0, 'BL1', '01/08/2025', ?)",
        (rid, prix_net, statut))
    conn.commit()


def test_factures_retro_200(tmp_path):
    assert _client(tmp_path).get("/factures-retro").status_code == 200


def test_facture_apercu_200(tmp_path):
    client = _client(tmp_path)
    conn, rid = _doc(client)
    _ligne(conn, rid)
    r = client.get(f"/facture/{rid}")
    assert r.status_code == 200
    assert "PRODUIT A" in r.text


def test_facture_csv_non_bloquee(tmp_path):
    client = _client(tmp_path)
    conn, rid = _doc(client)
    _ligne(conn, rid)
    r = client.get(f"/facture/{rid}/csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "PRODUIT A" in r.text


def test_facture_pdf_bloquee_renvoie_409(tmp_path):
    client = _client(tmp_path)
    conn, rid = _doc(client)
    _ligne(conn, rid, statut="resolu")
    _ligne(conn, rid, statut="rouge", prix_net=0.0)
    assert client.get(f"/facture/{rid}/pdf").status_code == 409


def test_facture_inconnue_404(tmp_path):
    assert _client(tmp_path).get("/facture/999/csv").status_code == 404
