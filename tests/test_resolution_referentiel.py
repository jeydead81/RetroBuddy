from app.db import get_connection, init_db
from app.temps2.calcul_prix import prix_a_date
from app.temps3.resolution import enregistrer_ligne


def _conn(tmp_path):
    c = get_connection(tmp_path / "t.db")
    init_db(c)
    c.execute("INSERT INTO retro_documents (id, fichier) VALUES (1, 'r.pdf')")
    return c


def _ligne(c, code, bl_date, statut="rouge"):
    cur = c.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, qte, bl_date, statut_ecart) "
        "VALUES (1, 'X', ?, 2, ?, ?)", (code, bl_date, statut))
    c.commit()
    return cur.lastrowid


# --------- prix_a_date : source résolution ±6 mois, priorité labo ---------

def _ref(c, code, date, net, source="facture"):
    c.execute("INSERT INTO referentiel_prix (code, date_facture, prix_net, source) "
              "VALUES (?, ?, ?, ?)", (code, date, net, source))
    c.commit()


def test_prix_resolution_valable_dans_6_mois(tmp_path):
    c = _conn(tmp_path)
    _ref(c, "C", "01/03/2025", 4.5, source="resolution")
    assert prix_a_date(c, "C", "01/08/2025")["prix_net"] == 4.5      # +5 mois -> OK
    assert prix_a_date(c, "C", "01/12/2024")["prix_net"] == 4.5      # -3 mois -> OK


def test_prix_resolution_hors_6_mois_refuse(tmp_path):
    c = _conn(tmp_path)
    _ref(c, "C", "01/03/2025", 4.5, source="resolution")
    assert prix_a_date(c, "C", "01/11/2025") is None                # +8 mois -> hors fenêtre


def test_prix_labo_prioritaire_sur_resolution(tmp_path):
    c = _conn(tmp_path)
    _ref(c, "C", "01/03/2025", 9.9, source="resolution")           # saisie utilisateur
    _ref(c, "C", "10/07/2025", 4.5, source="facture")              # vraie facture, antérieure
    assert prix_a_date(c, "C", "01/08/2025")["prix_net"] == 4.5     # le labo gagne


# --------- enregistrer_ligne : alimente le référentiel + propage ---------

def test_saisie_alimente_referentiel_et_propage(tmp_path):
    c = _conn(tmp_path)
    saisie = _ligne(c, "3400930000007", "10/06/2025")              # celle qu'on renseigne
    proche = _ligne(c, "3400930000007", "20/09/2025")              # +3 mois, même code -> propagée
    loin = _ligne(c, "3400930000007", "01/02/2026")               # +8 mois -> hors fenêtre
    autre = _ligne(c, "3400931000005", "20/06/2025")              # autre code -> non touchée

    res = enregistrer_ligne(c, saisie, prix_brut=6.0, remise_pct=10.0, prix_net=5.0)
    assert res["statut_ecart"] == "resolu"
    assert res["propagees"] == 1                                   # seule 'proche' est résolue

    # référentiel alimenté, source resolution
    ref = c.execute("SELECT prix_net, source FROM referentiel_prix WHERE code='3400930000007'").fetchone()
    assert ref["prix_net"] == 5.0 and ref["source"] == "resolution"

    statuts = {r["id"]: r["statut_ecart"] for r in c.execute("SELECT id, statut_ecart FROM retro_lignes")}
    assert statuts[proche] == "resolu"
    assert statuts[loin] == "rouge"
    assert statuts[autre] == "rouge"


def test_saisie_nette_nulle_n_alimente_pas(tmp_path):
    c = _conn(tmp_path)
    lid = _ligne(c, "3400930000007", "10/06/2025")
    enregistrer_ligne(c, lid, prix_net=0.0)                        # pas de prix valide
    assert c.execute("SELECT COUNT(*) n FROM referentiel_prix").fetchone()["n"] == 0
