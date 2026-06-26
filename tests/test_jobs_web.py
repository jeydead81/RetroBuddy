import time

from fastapi.testclient import TestClient

from app.main import creer_app, get_extractor, get_retro_extractor
from app.temps1.extraction_ia import MockExtractor
from app.temps1.schemas import EnteteFacture, FactureExtraite, LigneFacture
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne


def _facture():
    return FactureExtraite(
        type_document="facture_marchandise",
        entete=EnteteFacture(labo="URGO", date_facture="2026-01-10", total_ht_affiche=10.0),
        lignes=[LigneFacture(code="3400930000007", designation="X", prix_brut=6.0,
                             remise_pct=10.0, prix_net=5.0, montant_ht=10.0)])


def _retro():
    return RetroExtrait(type_document="retro_lgo",
                        entete=RetroEntete(pharmacie_emettrice="A", pharmacie_destinataire="B"),
                        lignes=[RetroLigne(designation="X", code="3400930000007", qte=1, tva=10.0,
                                           bl_numero="BL1", bl_date="01/08/2025")])


def _attendre_fin(client, url_progress, job_id):
    for _ in range(50):
        j = client.get(f"{url_progress}/{job_id}").json()
        if j.get("termine"):
            return j
        time.sleep(0.1)
    raise AssertionError("job non terminé")


def test_ingest_start_et_progress_labo(tmp_path):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_extractor] = lambda: MockExtractor(defaut=_facture())
    client = TestClient(app)
    r = client.post("/ingest/start",
                    files=[("fichiers", ("f.pdf", b"%PDF", "application/pdf"))]).json()
    assert r["total"] == 1 and "job_id" in r
    j = _attendre_fin(client, "/ingest/progress", r["job_id"])
    assert j["fait"] == 1
    assert j["details"][0]["statut"] == "ingeree"


def test_retro_start_et_progress(tmp_path):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_retro_extractor] = lambda: MockExtractor(defaut=_retro())
    client = TestClient(app)
    r = client.post("/retro/ingest/start",
                    files=[("fichiers", ("r.pdf", b"%PDF", "application/pdf"))]).json()
    assert r["total"] == 1
    j = _attendre_fin(client, "/retro/progress", r["job_id"])
    assert j["fait"] == 1
    assert "n_lignes" in j["details"][0]


def test_progress_job_inconnu(tmp_path):
    client = TestClient(creer_app(db_path=str(tmp_path / "web.db")))
    assert client.get("/ingest/progress/zzz").json() == {"introuvable": True}
