import io
import zipfile

from fastapi.testclient import TestClient

from app.db import get_connection
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


def test_facture_paye_toggle(tmp_path):
    client = _client(tmp_path)
    conn, rid = _doc(client)
    assert client.post(f"/facture/{rid}/paye", json={"paye": True}).json()["paye"] is True
    c = get_connection(client.app.state.db_path)
    assert c.execute("SELECT paye FROM retro_documents WHERE id=?", (rid,)).fetchone()["paye"] == 1
    assert client.post(f"/facture/{rid}/paye", json={"paye": False}).json()["paye"] is False
    assert c.execute("SELECT paye FROM retro_documents WHERE id=?", (rid,)).fetchone()["paye"] == 0


def test_facture_paye_404(tmp_path):
    assert _client(tmp_path).post("/facture/999/paye", json={"paye": True}).status_code == 404


def test_telecharger_lot_exclut_incompletes(tmp_path):
    client = _client(tmp_path)
    conn, rid_ok = _doc(client)
    _ligne(conn, rid_ok, statut="resolu")                 # complète -> incluse
    conn2, rid_ko = _doc(client)
    _ligne(conn2, rid_ko, statut="rouge", prix_net=0.0)   # à compléter -> exclue
    r = client.post("/factures-retro/telecharger", json={"ids": [rid_ok, rid_ko]})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["x-factures-inclus"] == "1"
    assert r.headers["x-factures-exclus"] == "1"
    noms = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert noms == [f"facture_{rid_ok}.pdf"]


def test_telecharger_lot_aucune_complete_409(tmp_path):
    client = _client(tmp_path)
    conn, rid_ko = _doc(client)
    _ligne(conn, rid_ko, statut="rouge", prix_net=0.0)
    assert client.post("/factures-retro/telecharger", json={"ids": [rid_ko]}).status_code == 409
