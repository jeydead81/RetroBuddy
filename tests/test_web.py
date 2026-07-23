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
    assert "ingérée" in r.text.lower() or "ingeree" in r.text.lower()
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
    # Deux PDF aux octets DIFFÉRENTS (des octets identiques seraient dédupliqués).
    client = _client(tmp_path)
    f1 = {"fichier": ("f.pdf", b"%PDF-1.4 fake 1", "application/pdf")}
    f2 = {"fichier": ("g.pdf", b"%PDF-1.4 fake 2", "application/pdf")}
    assert client.post("/ingest-un", files=f1).json()["n_total"] == 1
    assert client.post("/ingest-un", files=f2).json()["n_total"] == 2


def test_accueil_affiche_total_en_base(tmp_path):
    client = _client(tmp_path)
    client.post("/ingest-un", files={"fichier": ("f.pdf", b"%PDF", "application/pdf")})
    assert "déjà en base" in client.get("/import-labos").text.lower()


def test_ingest_un_renvoie_cout(tmp_path):
    client = _client(tmp_path)
    r = client.post("/ingest-un", files={"fichier": ("f.pdf", b"%PDF", "application/pdf")}).json()
    assert "cout" in r
    assert "cout_total" in r


def test_accueil_affiche_cout_cumule(tmp_path):
    assert "coût cumulé" in _client(tmp_path).get("/import-labos").text.lower()


def test_home_page_200(tmp_path):
    r = _client(tmp_path).get("/")
    assert r.status_code == 200
    assert "retrobuddy" in r.text.lower()  # page de présentation


def _ajouter_referentiel(client, code="ABC", date="2026-01-10",
                         brut=10.0, remise=10.0, net=9.0, modifie=0):
    from app.db import get_connection
    c = get_connection(client.app.state.db_path)
    c.execute(
        "INSERT INTO referentiel_prix (code, date_facture, type_code, labo, "
        "prix_brut, remise_pct, prix_net, designation, modifie_manuellement) "
        "VALUES (?, ?, 'cip', 'URGO', ?, ?, ?, 'X', ?)",
        (code, date, brut, remise, net, modifie))
    c.commit()


def test_referentiel_maj_recalcule_le_net(tmp_path):
    client = _client(tmp_path)
    _ajouter_referentiel(client, brut=20.0, remise=25.0, net=99.0)
    r = client.post("/referentiel/maj",
                    json={"code": "ABC", "date_facture": "2026-01-10",
                          "prix_brut": 20.0, "remise_pct": 25.0, "prix_net": None})
    assert r.status_code == 200
    assert r.json()["prix_net"] == 15.0          # 20 * (1 - 0.25)
    # persistance + marquage manuel
    from app.db import get_connection
    row = get_connection(client.app.state.db_path).execute(
        "SELECT prix_net, modifie_manuellement FROM referentiel_prix "
        "WHERE code='ABC' AND date_facture='2026-01-10'").fetchone()
    assert row["prix_net"] == 15.0
    assert row["modifie_manuellement"] == 1


def test_referentiel_maj_introuvable_404(tmp_path):
    client = _client(tmp_path)
    r = client.post("/referentiel/maj",
                    json={"code": "ZZZ", "date_facture": "2099-01-01",
                          "prix_brut": 1.0, "remise_pct": 0.0, "prix_net": 1.0})
    assert r.status_code == 404
