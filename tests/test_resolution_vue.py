from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _ligne(c, designation, statut, saisie=0):
    c.execute(
        "INSERT INTO retro_lignes (retro_id, designation, statut_ecart, saisie_manuelle) "
        "VALUES (1, ?, ?, ?)", (designation, statut, saisie))


def test_resolution_compteurs(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO retro_documents (id, fichier) VALUES (1, 'r.pdf')")
    for i in range(3):
        _ligne(c, f"AUTO{i}", "resolu", saisie=0)     # rapprochées automatiquement
    _ligne(c, "MANUEL", "resolu", saisie=1)            # complétée à la main
    for i in range(2):
        _ligne(c, f"ROUGE{i}", "rouge")               # à compléter
    c.commit()
    t = client.get("/resolution").text
    assert "Rapprochées auto : 3" in t                 # plus le compteur trompeur à 0
    assert "Complétées à la main : 1" in t
    assert "À compléter : 2" in t


def test_resolution_recherche(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO retro_documents (id, fichier) VALUES (1, 'r.pdf')")
    _ligne(c, "NICOPASS PAST", "rouge")
    _ligne(c, "DOLIPRANE 1000", "rouge")
    c.commit()
    t = client.get("/resolution?q=NICO").text
    assert "NICOPASS PAST" in t
    assert "DOLIPRANE 1000" not in t                   # filtré


def test_retro_lignes_compteurs_et_filtre(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO retro_documents (id, fichier, numero) VALUES (1, 'r.pdf', 'F1')")
    _ligne(c, "AUTO", "resolu")
    _ligne(c, "ROUGE1", "rouge")
    _ligne(c, "ROUGE2", "rouge")
    c.commit()
    t = client.get("/retro-lignes").text
    assert "Rapprochées : 1" in t
    assert "À compléter : 2" in t
    fr = client.get("/retro-lignes?statut=rouge").text       # filtre clic-bouton
    assert "ROUGE1" in fr and "ROUGE2" in fr
    assert "AUTO" not in fr                                   # rapprochée -> exclue du filtre


def test_factures_lgpi_colonne_rapprochees(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO retro_documents (id, fichier, numero) VALUES (1, 'r.pdf', 'F1')")
    _ligne(c, "A", "resolu")
    _ligne(c, "B", "rouge")
    c.commit()
    t = client.get("/factures-retro").text
    assert "Rapprochées" in t
    assert "1 / 2" in t                                       # 1 résolue sur 2 lignes


def test_resolution_pagination(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO retro_documents (id, fichier) VALUES (1, 'r.pdf')")
    for i in range(120):
        _ligne(c, f"LIGNE{i:03d}", "rouge")
    c.commit()
    p1 = client.get("/resolution").text
    assert p1.count("data-id=") == 50 + 1              # 50 lignes/page (+1 dans le JS)
    assert "Suivant" in p1
    assert client.get("/resolution?page=3").status_code == 200
