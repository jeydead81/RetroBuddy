from app.db import get_connection, init_db
from app.temps1.recuperation import factures_recuperables, recuperer_en_revue


def _conn(tmp_path):
    c = get_connection(tmp_path / "t.db")
    init_db(c)
    return c


def _facture(c, fid, ta, tc, motif="totaux non réconciliés (Sonnet + Opus)"):
    c.execute(
        "INSERT INTO factures (id, fichier, labo, date_facture, statut, motif, "
        "total_affiche, total_calcule) VALUES (?, 'f.pdf', 'LABO', '01/03/2025', "
        "'en_revue', ?, ?, ?)", (fid, motif, ta, tc))
    c.commit()


def _ligne(c, fid, code, net, montant):
    c.execute(
        "INSERT INTO lignes_facture (facture_id, code, designation, qte, prix_brut, "
        "remise_pct, prix_net, montant_ht, tva) VALUES (?, ?, 'X', 1, ?, 10.0, ?, ?, 20.0)",
        (fid, code, net + 1, net, montant))
    c.commit()


def test_recupere_facture_avec_deduction(tmp_path):
    c = _conn(tmp_path)
    _facture(c, 1, ta=545.53, tc=551.04)                 # Σ 551,04 >= net 545,53 -> déduction
    _ligne(c, 1, "3400930000007", 545.53, 545.53)
    _ligne(c, 1, "4006381333931", 5.51, 5.51)
    n_fact, n_ref = recuperer_en_revue(c, 1.0)
    assert n_fact == 1 and n_ref == 2
    assert c.execute("SELECT statut FROM factures WHERE id=1").fetchone()[0] == "ingeree"
    assert c.execute("SELECT COUNT(*) FROM referentiel_prix").fetchone()[0] == 2


def test_recupere_calcule_le_net_manquant(tmp_path):
    c = _conn(tmp_path)
    _facture(c, 1, ta=100.0, tc=110.0)                   # Σ 110 >= net 100 -> déduction
    # ligne SANS prix_net (montant + brut + remise présents) : doit être reconstituée
    c.execute(
        "INSERT INTO lignes_facture (facture_id, code, designation, qte, prix_brut, "
        "remise_pct, prix_net, montant_ht, tva) VALUES "
        "(1, '3400930000007', 'X', 2, 60.0, 8.0, NULL, 110.0, 20.0)")
    c.commit()
    n_fact, n_ref = recuperer_en_revue(c, 1.0)
    assert n_fact == 1 and n_ref == 1                    # net calculé -> exploitable -> référentiel
    assert c.execute("SELECT prix_net FROM lignes_facture WHERE facture_id=1").fetchone()[0] \
        == round(60.0 * 0.92, 4)                         # brut×(1−remise)
    assert c.execute("SELECT COUNT(*) FROM referentiel_prix WHERE code='3400930000007'").fetchone()[0] == 1


def test_ne_recupere_pas_si_lignes_manquantes(tmp_path):
    c = _conn(tmp_path)
    _facture(c, 1, ta=970.99, tc=910.99)                 # Σ 910,99 < net 970,99 -> lignes manquent
    _ligne(c, 1, "3400930000007", 910.99, 910.99)
    assert factures_recuperables(c, 1.0) == []
    n_fact, _ = recuperer_en_revue(c, 1.0)
    assert n_fact == 0
    assert c.execute("SELECT statut FROM factures WHERE id=1").fetchone()[0] == "en_revue"


def test_ne_touche_pas_en_revue_classification(tmp_path):
    c = _conn(tmp_path)
    _facture(c, 1, ta=100.0, tc=110.0,
             motif="classé « abonnement » mais contient des lignes produit")   # pas « concili »
    _ligne(c, 1, "3400930000007", 110.0, 110.0)
    assert factures_recuperables(c, 1.0) == []
    recuperer_en_revue(c, 1.0)
    assert c.execute("SELECT statut FROM factures WHERE id=1").fetchone()[0] == "en_revue"
