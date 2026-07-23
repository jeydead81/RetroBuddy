import time

from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _seed(c, n_rouge):
    c.execute("INSERT INTO retro_documents (id, fichier) VALUES (1, 'r.pdf')")
    c.execute("INSERT INTO referentiel_prix (code, date_facture, prix_net) "
              "VALUES ('3400930000007', '01/08/2025', 4.5)")
    for i in range(n_rouge):
        c.execute("INSERT INTO retro_lignes (retro_id, designation, code, bl_date, "
                  "statut_ecart) VALUES (1, ?, '3400930000007', '10/08/2025', 'rouge')",
                  (f"L{i}",))
    c.commit()


def _attendre(client, job_id, timeout=10):
    debut = time.monotonic()
    while time.monotonic() - debut < timeout:
        j = client.get(f"/resolution/rematch/progress/{job_id}").json()
        if j.get("termine"):
            return j
        time.sleep(0.03)
    raise AssertionError("job non terminé")


def test_rematch_job_progression_et_resultat(tmp_path):
    client = _client(tmp_path)
    _seed(get_connection(client.app.state.db_path), 60)
    r = client.post("/resolution/rematch/start").json()
    assert r["total"] == 60
    j = _attendre(client, r["job_id"])
    assert j["fait"] == 60                                  # barre arrivée à 100 %
    assert j["details"][0]["resultat"]["resolu"] == 60     # code résolu -> résolues
    c = get_connection(client.app.state.db_path)
    assert c.execute("SELECT COUNT(*) n FROM retro_lignes WHERE statut_ecart='resolu'"
                     ).fetchone()["n"] == 60


def test_rematch_job_vide(tmp_path):
    client = _client(tmp_path)
    r = client.post("/resolution/rematch/start").json()
    assert r["total"] == 0
    j = _attendre(client, r["job_id"])
    assert j["termine"] and j["fait"] == 0


def test_rematch_progress_introuvable(tmp_path):
    client = _client(tmp_path)
    assert client.get("/resolution/rematch/progress/inexistant").json()["introuvable"]
