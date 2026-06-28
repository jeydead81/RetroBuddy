from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _seed_en_revue(c):
    c.execute(
        "INSERT INTO factures (id, fichier, labo, date_facture, type_document, statut, "
        "motif, total_affiche, total_calcule) VALUES "
        "(1, 'a.pdf', 'URGO', '06/01/2025', 'facture_marchandise', 'en_revue', "
        "'totaux non réconciliés (Sonnet + Opus)', 100.0, 90.0)")
    # ligne valide (CIP13 correct) qté×net = montant -> cohérente
    c.execute(
        "INSERT INTO lignes_facture (facture_id, code, type_code, designation, qte, "
        "prix_brut, remise_pct, prix_net, montant_ht, checksum_ok, valide) VALUES "
        "(1, '3400930000007', 'CIP13', 'DOLIPRANE', 2, 6.0, 10.0, 5.0, 10.0, 1, 1)")
    c.commit()


def test_detail_facture_labo_200(tmp_path):
    client = _client(tmp_path)
    _seed_en_revue(get_connection(client.app.state.db_path))
    r = client.get("/facture-labo/1")
    assert r.status_code == 200
    assert "DOLIPRANE" in r.text
    assert "intégrer au référentiel" in r.text          # bouton visible (en_revue)


def test_detail_signale_ligne_incoherente(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO factures (id, fichier, statut, total_affiche) "
              "VALUES (1, 'b.pdf', 'en_revue', 50.0)")
    # qté×net = 2×5 = 10, mais montant affiché 42 -> incohérent
    c.execute("INSERT INTO lignes_facture (facture_id, code, designation, qte, prix_net, "
              "montant_ht, checksum_ok, valide) "
              "VALUES (1, '3400930000007', 'X', 2, 5.0, 42.0, 1, 1)")
    c.commit()
    r = client.get("/facture-labo/1")
    assert "incoherent" in r.text                        # ligne mise en évidence


def test_integrer_ajoute_au_referentiel_et_ingere(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    _seed_en_revue(c)
    client.post("/facture-labo/1/integrer")
    ref = c.execute("SELECT code, prix_net FROM referentiel_prix").fetchall()
    assert len(ref) == 1
    assert ref[0]["code"] == "3400930000007"
    assert ref[0]["prix_net"] == 5.0
    statut = c.execute("SELECT statut FROM factures WHERE id=1").fetchone()["statut"]
    assert statut == "ingeree"                           # plus « en revue »


def test_integrer_ignore_lignes_non_valides(tmp_path):
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO factures (id, fichier, labo, date_facture, statut) "
              "VALUES (1, 'c.pdf', 'URGO', '06/01/2025', 'en_revue')")
    c.execute("INSERT INTO lignes_facture (facture_id, code, designation, prix_net, valide) "
              "VALUES (1, '3400930000007', 'OK', 5.0, 1)")
    c.execute("INSERT INTO lignes_facture (facture_id, code, designation, prix_net, valide) "
              "VALUES (1, '3400930000000', 'KO', 9.0, 0)")   # checksum invalide -> exclue
    c.commit()
    client.post("/facture-labo/1/integrer")
    ref = c.execute("SELECT code FROM referentiel_prix").fetchall()
    assert [r["code"] for r in ref] == ["3400930000007"]


def test_facture_ingere_sans_prix_net_signale(tmp_path):
    # Cas PiLeJe : montant présent mais PA net non extrait -> 0 prix au référentiel.
    client = _client(tmp_path)
    c = get_connection(client.app.state.db_path)
    c.execute("INSERT INTO factures (id, fichier, statut, total_affiche) "
              "VALUES (1, 'pileje.pdf', 'ingeree', 140.53)")
    c.execute("INSERT INTO lignes_facture (facture_id, code_interne, designation, qte, "
              "prix_brut, remise_pct, montant_ht, valide) "
              "VALUES (1, '6316863', 'CHRONOBIANE', 12, 16.73, 30.0, 140.53, 0)")
    c.commit()
    d = client.get("/facture-labo/1").text
    assert "PA net non extrait" in d                   # pas un faux « ≠ montant »
    assert "aucun prix versé au référentiel" in d      # bandeau d'alerte
    assert "30.00" in d                                 # remise affichée


def test_detail_inexistant_redirige(tmp_path):
    client = _client(tmp_path)
    r = client.get("/facture-labo/999", follow_redirects=False)
    assert r.status_code == 303
