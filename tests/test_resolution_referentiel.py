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


def test_correction_prime_tant_que_pas_de_labo_plus_recent(tmp_path):
    c = _conn(tmp_path)
    _ref(c, "C", "01/03/2025", 4.5, source="facture")              # ancien prix labo
    _ref(c, "C", "10/07/2025", 9.9, source="resolution")           # correction plus récente
    assert prix_a_date(c, "C", "01/08/2025")["prix_net"] == 9.9     # la correction fait autorité


def test_labo_plus_recent_reprend_la_main(tmp_path):
    c = _conn(tmp_path)
    _ref(c, "C", "01/03/2025", 9.9, source="resolution")           # ancienne correction
    _ref(c, "C", "10/07/2025", 4.5, source="facture")              # facture importée APRÈS
    assert prix_a_date(c, "C", "01/08/2025")["prix_net"] == 4.5     # le nouveau prix labo reprend la main


def test_prix_labo_seul_sans_correction(tmp_path):
    c = _conn(tmp_path)
    _ref(c, "C", "10/07/2025", 4.5, source="facture")              # aucune correction : labo
    assert prix_a_date(c, "C", "01/08/2025")["prix_net"] == 4.5


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


def test_correction_propage_sur_soeur_verte_meme_facture(tmp_path):
    c = _conn(tmp_path)
    a = _ligne(c, "3400930000007", "10/06/2025")                   # ligne qu'on corrige
    b = _ligne(c, "3400930000007", "15/06/2025", statut="resolu")  # sœur déjà verte, même facture
    c.execute("UPDATE retro_lignes SET prix_net=99.0 WHERE id=?", (b,))
    c.commit()

    enregistrer_ligne(c, a, prix_brut=6.0, remise_pct=10.0, prix_net=5.0)
    assert c.execute("SELECT prix_net FROM retro_lignes WHERE id=?", (b,)).fetchone()["prix_net"] == 5.0


def test_correction_ne_touche_pas_soeur_verte_autre_facture(tmp_path):
    c = _conn(tmp_path)
    c.execute("INSERT INTO retro_documents (id, fichier) VALUES (2, 'r2.pdf')")
    a = _ligne(c, "3400930000007", "10/06/2025")
    cur = c.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, qte, bl_date, statut_ecart, prix_net) "
        "VALUES (2, 'X', '3400930000007', 2, '15/06/2025', 'resolu', 99.0)")             # autre facture
    b = cur.lastrowid
    c.commit()

    enregistrer_ligne(c, a, prix_brut=6.0, remise_pct=10.0, prix_net=5.0)
    # intacte : une facture déjà rapprochée n'est pas modifiée en douce (Re-rapprocher s'en charge).
    assert c.execute("SELECT prix_net FROM retro_lignes WHERE id=?", (b,)).fetchone()["prix_net"] == 99.0
