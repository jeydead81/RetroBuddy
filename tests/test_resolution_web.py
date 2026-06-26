from fastapi.testclient import TestClient

from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _ligne(client, **kw):
    from app.db import get_connection
    conn = get_connection(client.app.state.db_path)
    conn.execute("INSERT OR IGNORE INTO retro_documents (id, numero) VALUES (1, 'N1')")
    base = dict(retro_id=1, designation="REXORUBIA", qte=2.0, statut_ecart="rouge",
                valide_utilisateur=0, saisie_manuelle=0)
    base.update(kw)
    cols = ", ".join(base); ph = ", ".join("?" for _ in base)
    cur = conn.execute(f"INSERT INTO retro_lignes ({cols}) VALUES ({ph})", tuple(base.values()))
    conn.commit()
    return cur.lastrowid


def test_page_resolution_200(tmp_path):
    assert _client(tmp_path).get("/resolution").status_code == 200


def test_resolution_masque_les_resolus(tmp_path):
    client = _client(tmp_path)
    _ligne(client, designation="ROUGE_VISIBLE", statut_ecart="rouge")
    _ligne(client, designation="VERT_CACHE", statut_ecart="resolu")
    html = client.get("/resolution").text
    assert "ROUGE_VISIBLE" in html
    assert "VERT_CACHE" not in html


def test_enregistrer_ligne_endpoint(tmp_path):
    client = _client(tmp_path)
    lid = _ligne(client)
    r = client.post(f"/resolution/ligne/{lid}",
                    json={"prix_brut": 10.0, "remise_pct": 20.0, "ug": 0})
    assert r.status_code == 200
    assert r.json()["prix_net"] == 8.0


def test_accepter_et_refuser(tmp_path):
    client = _client(tmp_path)
    lid = _ligne(client, statut_ecart="orange", prix_net=4.5, code_resolu="C")
    assert client.post(f"/resolution/ligne/{lid}/accepter").status_code == 200
    lid2 = _ligne(client, statut_ecart="orange", prix_net=4.5, code_resolu="C")
    assert client.post(f"/resolution/ligne/{lid2}/refuser").status_code == 200


def test_rematch_endpoint(tmp_path):
    r = _client(tmp_path).post("/resolution/rematch")
    assert r.status_code == 200
    assert "resolu" in r.json()
