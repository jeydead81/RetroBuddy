from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _seed(client, n):
    c = get_connection(client.app.state.db_path)
    for i in range(n):
        c.execute(
            "INSERT INTO referentiel_prix (code, date_facture, labo, designation, prix_net) "
            "VALUES (?, '2025-08-01', 'URGO', ?, 1.0)",
            (f"C{i:04d}", f"PRODUIT {i}"))
    c.commit()


def test_pagination_50_par_page(tmp_path):
    client = _client(tmp_path)
    _seed(client, 120)
    h = client.get("/referentiel").text
    assert "sur 120" in h
    assert h.count('data-code="') == 50            # 50 lignes en page 1
    assert "page 1 / 3" in h


def test_page_2_tranche_suivante(tmp_path):
    client = _client(tmp_path)
    _seed(client, 120)
    h = client.get("/referentiel?page=2").text
    assert "page 2 / 3" in h
    assert "C0050" in h and "C0049" not in h       # 2e tranche (tri par code)


def test_recherche_filtre(tmp_path):
    client = _client(tmp_path)
    _seed(client, 120)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO referentiel_prix (code, date_facture, labo, designation, prix_net) "
              "VALUES ('ZZZ', '2025-08-01', 'BIOGARAN', 'DOLIPRANE', 1.0)")
    c.commit()
    h = client.get("/referentiel?q=DOLIPRANE").text
    assert "ZZZ" in h
    assert "PRODUIT 1" not in h                     # les autres sont filtrés


def test_recherche_sans_resultat(tmp_path):
    client = _client(tmp_path)
    _seed(client, 5)
    h = client.get("/referentiel?q=INTROUVABLE").text
    assert "Aucun résultat" in h


def test_factures_lgpi_pagination_group_by(tmp_path):
    # La liste LGPI fait un GROUP BY : on vérifie que le comptage paginé reste juste.
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    for k in range(60):
        c.execute("INSERT INTO retro_documents (numero) VALUES (?)", (f"R{k:03d}",))
    c.commit()
    h = client.get("/factures-retro").text
    assert "sur 60" in h
    assert "page 1 / 2" in h
    assert "R059" in h and "R009" not in h        # tri d.id DESC -> derniers d'abord
