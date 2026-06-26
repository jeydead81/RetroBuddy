from fastapi.testclient import TestClient

from app.main import creer_app, get_extractor
from app.temps1.extraction_ia import MockExtractor
from app.temps1.schemas import EnteteFacture, FactureExtraite, LigneFacture


def _facture():
    return FactureExtraite(
        type_document="facture_marchandise",
        entete=EnteteFacture(labo="URGO", numero_facture="F1",
                             date_facture="2026-01-10", total_ht_affiche=10.0),
        lignes=[LigneFacture(code="3400930000007", designation="X", prix_brut=6.0,
                             remise_pct=10.0, prix_net=5.0, montant_ht=10.0)],
    )


def _client(tmp_path):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_extractor] = lambda: MockExtractor(defaut=_facture())
    return TestClient(app)


def test_accueil_200(tmp_path):
    assert _client(tmp_path).get("/").status_code == 200


def test_factures_vide_200(tmp_path):
    r = _client(tmp_path).get("/factures")
    assert r.status_code == 200


def test_ingest_ajoute_au_referentiel(tmp_path):
    client = _client(tmp_path)
    files = [("fichiers", ("f.pdf", b"%PDF-1.4 fake", "application/pdf"))]
    r = client.post("/ingest", files=files)
    assert r.status_code == 200
    assert "ingérée" in r.text or "ingeree" in r.text.lower()
    ref = client.get("/referentiel")
    assert "3400930000007" in ref.text


def test_ingest_un_renvoie_json(tmp_path):
    client = _client(tmp_path)
    files = {"fichier": ("f.pdf", b"%PDF-1.4 fake", "application/pdf")}
    r = client.post("/ingest-un", files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["statut"] == "ingeree"
    assert data["fichier"] == "f.pdf"
    assert data["n_total"] == 1


def test_ingest_un_compteur_total_incremente(tmp_path):
    client = _client(tmp_path)
    f = {"fichier": ("f.pdf", b"%PDF-1.4 fake", "application/pdf")}
    assert client.post("/ingest-un", files=f).json()["n_total"] == 1
    assert client.post("/ingest-un", files=f).json()["n_total"] == 2


def test_accueil_affiche_total_en_base(tmp_path):
    client = _client(tmp_path)
    client.post("/ingest-un", files={"fichier": ("f.pdf", b"%PDF", "application/pdf")})
    assert "déjà en base" in client.get("/").text.lower()


def test_ingest_un_renvoie_cout(tmp_path):
    client = _client(tmp_path)
    r = client.post("/ingest-un", files={"fichier": ("f.pdf", b"%PDF", "application/pdf")}).json()
    assert "cout" in r
    assert "cout_total" in r


def test_accueil_affiche_cout_cumule(tmp_path):
    assert "coût cumulé" in _client(tmp_path).get("/").text.lower()
