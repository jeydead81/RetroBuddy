from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _seed_bloquee(c):
    c.execute("INSERT INTO retro_documents (id, fichier, pharmacie_emettrice, "
              "pharmacie_destinataire, numero, date_vente) "
              "VALUES (1, 'r.pdf', 'PHIE A', 'PHIE B', 'F1', '01/09/2025')")
    # une ligne résolue (facturable) + une rouge (non rapprochée -> exclue du total)
    c.execute("INSERT INTO retro_lignes (retro_id, designation, qte, prix_net, tva, "
              "statut_ecart, bl_numero, bl_date) VALUES "
              "(1, 'OK', 2, 5.0, 20.0, 'resolu', 'BL1', '01/09/2025')")
    c.execute("INSERT INTO retro_lignes (retro_id, designation, qte, statut_ecart) "
              "VALUES (1, 'MANQUE', 3, 'rouge')")
    c.commit()


def test_export_bloque_sans_forcer(tmp_path):
    client = _client(tmp_path)
    _seed_bloquee(get_connection(client.app.state.db_path))
    assert client.get("/facture/1/pdf").status_code == 409
    assert client.get("/facture/1/csv").status_code == 409
    assert client.get("/facture/1/xlsx").status_code == 409


def test_export_force_partielle(tmp_path):
    client = _client(tmp_path)
    _seed_bloquee(get_connection(client.app.state.db_path))
    pdf = client.get("/facture/1/pdf?forcer=1")
    assert pdf.status_code == 200
    assert pdf.content[:5] == b"%PDF-"
    csv = client.get("/facture/1/csv?forcer=1")
    assert "FACTURE PARTIELLE" in csv.text
    assert "1 ligne(s) non rapprochée(s)" in csv.text    # n_rouge = 1
