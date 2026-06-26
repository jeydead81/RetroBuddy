from fastapi.testclient import TestClient

from app.main import creer_app, get_retro_extractor
from app.temps1.extraction_ia import MockExtractor
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne


def _retro():
    return RetroExtrait(
        type_document="retro_lgo",
        entete=RetroEntete(pharmacie_emettrice="SERALY", pharmacie_destinataire="CENON",
                           date_vente="22/09/2025", numero="N1"),
        lignes=[RetroLigne(designation="IMODIUMDUO CPR 12", code="3400937882248",
                           type_code="CIP13", qte=2, tva=10.0,
                           bl_numero="28476", bl_date="01/08/2025")])


def _client(tmp_path):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_retro_extractor] = lambda: MockExtractor(defaut=_retro())
    return TestClient(app)


def test_page_retro_200(tmp_path):
    assert _client(tmp_path).get("/retro").status_code == 200


def test_retro_ingest_un_renvoie_json(tmp_path):
    client = _client(tmp_path)
    r = client.post("/retro/ingest-un",
                    files={"fichier": ("retro.pdf", b"%PDF", "application/pdf")}).json()
    assert r["n_lignes"] == 1
    assert "n_resolu" in r and "n_rouge" in r
    assert "cout" in r and "cout_total" in r


def test_retro_lignes_200(tmp_path):
    client = _client(tmp_path)
    client.post("/retro/ingest-un",
                files={"fichier": ("retro.pdf", b"%PDF", "application/pdf")})
    r = client.get("/retro-lignes")
    assert r.status_code == 200
    assert "3400937882248" in r.text
