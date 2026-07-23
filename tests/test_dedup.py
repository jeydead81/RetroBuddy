from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import creer_app, get_extractor, get_retro_extractor
from app.temps1.extraction_ia import MockExtractor
from app.temps1.schemas import EnteteFacture, FactureExtraite, LigneFacture
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne, VentilationTvaLgo

PDF_A = b"%PDF-1.4 contenu A"
PDF_B = b"%PDF-1.4 contenu B different"


def _facture():
    return FactureExtraite(
        type_document="facture_marchandise",
        entete=EnteteFacture(labo="URGO", numero_facture="F1",
                             date_facture="10/01/2026", total_ht_affiche=10.0),
        lignes=[LigneFacture(code="3400930000007", designation="X", qte=2,
                             prix_brut=6.0, remise_pct=10.0, prix_net=5.0, montant_ht=10.0)])


def _retro():
    return RetroExtrait(
        type_document="retro_lgo",
        entete=RetroEntete(pharmacie_emettrice="A", pharmacie_destinataire="B",
                           date_vente="10/01/2026", numero="R1", total_ht_affiche=10.0,
                           ventilation=[VentilationTvaLgo(taux=10.0, montant_ht=10.0)]),
        lignes=[RetroLigne(designation="X", code="3400930000007", type_code="CIP13",
                           qte=1, tva=10.0, bl_numero="BL1", bl_date="05/01/2026",
                           montant_ht=10.0, prix_net_lgo=10.0)])


def _client_labo(tmp_path, mock):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_extractor] = lambda: mock
    return TestClient(app)


def test_meme_pdf_labo_pas_reextrait(tmp_path):
    mock = MockExtractor(defaut=_facture())
    client = _client_labo(tmp_path, mock)
    r1 = client.post("/ingest-un", files={"fichier": ("a.pdf", PDF_A, "application/pdf")})
    assert r1.json()["statut"] == "ingeree"
    n_appels = len(mock.appels)
    # Ré-import du MÊME fichier (même sous un autre nom) -> aucune extraction
    r2 = client.post("/ingest-un", files={"fichier": ("copie.pdf", PDF_A, "application/pdf")})
    assert r2.json()["statut"] == "ignoree"
    assert "identique" in r2.json()["motif"]
    assert r2.json()["cout"] == 0.0
    assert len(mock.appels) == n_appels                 # l'API n'a PAS été rappelée
    c = get_connection(client.app.state.db_path)
    assert c.execute("SELECT COUNT(*) n FROM factures").fetchone()["n"] == 1


def test_pdf_different_bien_extrait(tmp_path):
    mock = MockExtractor(defaut=_facture())
    client = _client_labo(tmp_path, mock)
    client.post("/ingest-un", files={"fichier": ("a.pdf", PDF_A, "application/pdf")})
    r2 = client.post("/ingest-un", files={"fichier": ("b.pdf", PDF_B, "application/pdf")})
    assert r2.json()["statut"] == "ingeree"             # octets différents -> traité


def test_meme_pdf_retro_pas_reextrait(tmp_path):
    mock = MockExtractor(defaut=_retro())
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_retro_extractor] = lambda: mock
    client = TestClient(app)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO referentiel_prix (code, date_facture, prix_net) "
              "VALUES ('3400930000007', '01/01/2026', 4.5)")
    c.commit()
    r1 = client.post("/retro/ingest-un", files={"fichier": ("r.pdf", PDF_A, "application/pdf")})
    assert r1.json()["n_lignes"] == 1
    n_appels = len(mock.appels)
    r2 = client.post("/retro/ingest-un", files={"fichier": ("r2.pdf", PDF_A, "application/pdf")})
    assert "identique" in r2.json().get("erreur", "")
    assert len(mock.appels) == n_appels
    assert c.execute("SELECT COUNT(*) n FROM retro_documents").fetchone()["n"] == 1
