from fastapi.testclient import TestClient

from app.config import charger_config, enregistrer_cle_api
from app.db import get_connection
from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _n(client, table):
    return get_connection(client.app.state.db_path).execute(
        f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]


def test_enregistrer_cle_preserve_le_reste(tmp_path):
    cfg = tmp_path / "config.local.yaml"
    cfg.write_text("model_defaut: claude-sonnet-4-6\nseuil_match_auto: 0.88\n", encoding="utf-8")
    enregistrer_cle_api("sk-ant-test123", chemin=str(cfg))
    data = charger_config(chemin=str(cfg))
    assert data["anthropic_api_key"] == "sk-ant-test123"
    assert data["model_defaut"] == "claude-sonnet-4-6"     # autres réglages préservés
    assert data["seuil_match_auto"] == 0.88


def test_reglages_200(tmp_path):
    assert _client(tmp_path).get("/reglages").status_code == 200


def test_cout_reset_baseline_non_destructif(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO factures (fichier, cout_estime) VALUES ('f.pdf', 0.05)")
    c.commit()
    assert "0.0500" in client.get("/import-labos").text        # coût visible avant reset
    client.post("/cout/reset/labo")
    assert "0.0000" in client.get("/import-labos").text        # vue remise à zéro (baseline)
    # la donnée n'est PAS supprimée
    assert c.execute("SELECT COUNT(*) n FROM factures").fetchone()["n"] == 1


def test_suppression_exige_le_mot(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO referentiel_prix (code, date_facture, prix_net) "
              "VALUES ('C', '01/08/2025', 4.5)")
    c.commit()
    client.post("/donnees/supprimer/referentiel", data={"confirmation": "oui"})
    assert _n(client, "referentiel_prix") == 1                 # mauvais mot -> rien supprimé
    client.post("/donnees/supprimer/referentiel", data={"confirmation": "SUPPRIMER"})
    assert _n(client, "referentiel_prix") == 0                 # bon mot -> supprimé


def test_suppression_factures_et_lignes(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO factures (id, fichier) VALUES (1, 'f.pdf')")
    c.execute("INSERT INTO lignes_facture (facture_id, designation) VALUES (1, 'X')")
    c.commit()
    client.post("/donnees/supprimer/factures", data={"confirmation": "SUPPRIMER"})
    assert _n(client, "factures") == 0
    assert _n(client, "lignes_facture") == 0


def test_suppression_retro_separee_du_labo(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO factures (id, fichier) VALUES (1, 'f.pdf')")          # labo
    c.execute("INSERT INTO retro_documents (id, fichier) VALUES (1, 'r.pdf')")   # rétro
    c.execute("INSERT INTO retro_lignes (retro_id, designation) VALUES (1, 'X')")
    c.commit()
    client.post("/donnees/supprimer/retro", data={"confirmation": "SUPPRIMER"})
    assert _n(client, "retro_documents") == 0
    assert _n(client, "retro_lignes") == 0
    assert _n(client, "factures") == 1                         # côté labo intact
