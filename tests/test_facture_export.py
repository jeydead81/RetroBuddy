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


def test_recontroler_revalide_sous_1euro(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO retro_documents (id, fichier, total_ht_affiche, total_ht_calcule, "
              "reconciliation_ok, motif_reconciliation) "
              "VALUES (1, 'r.pdf', 1215.78, 1215.84, 0, 'qté ou prix net manquant')")
    c.commit()
    r = client.post("/facture/1/recontroler")                # écart 6 centimes
    assert r.json()["ok"] is True
    assert c.execute("SELECT reconciliation_ok FROM retro_documents WHERE id=1").fetchone()[0] == 1


def test_recontroler_garde_ecart_significatif(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO retro_documents (id, fichier, total_ht_affiche, total_ht_calcule, "
              "reconciliation_ok) VALUES (1, 'r.pdf', 1000.0, 1005.0, 0)")   # écart 5 € > 1 €
    c.commit()
    r = client.post("/facture/1/recontroler")
    assert r.json()["ok"] is False
    assert c.execute("SELECT reconciliation_ok FROM retro_documents WHERE id=1").fetchone()[0] == 0


def test_facture_lignes_editables(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO retro_documents (id, fichier, numero) VALUES (1, 'r.pdf', 'F1')")
    c.execute("INSERT INTO retro_lignes (id, retro_id, designation, qte, prix_net, tva, "
              "statut_ecart, bl_numero, bl_date) VALUES "
              "(7, 1, 'OK', 2, 5.0, 20.0, 'resolu', 'BL1', '01/09/2025')")
    c.commit()
    page = client.get("/facture/1").text
    assert 'data-id="7"' in page                      # id de ligne exposé
    assert 'class="f-net"' in page                     # champ éditable
    # édition inline (réutilise l'endpoint résolution) -> persistée + saisie manuelle
    client.post("/resolution/ligne/7", json={"prix_brut": None, "remise_pct": None,
                                              "prix_net": 9.99, "ug": 0})
    row = c.execute("SELECT prix_net, saisie_manuelle FROM retro_lignes WHERE id=7").fetchone()
    assert row["prix_net"] == 9.99
    assert row["saisie_manuelle"] == 1                 # ne sera pas écrasée par un recalcul
