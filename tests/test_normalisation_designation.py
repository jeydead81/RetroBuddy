from app.db import get_connection, init_db
from app.temps2.normalisation_designation import (
    charger_abreviations, dosages_concordants, extraire_dosage,
    normaliser_designation, score_designation)


def test_normalise_majuscule_accents_ponctuation():
    assert normaliser_designation("Doliprane 1000mg, cpr.") == "DOLIPRANE 1000MG CPR"


def test_normalise_chaine_vide():
    assert normaliser_designation(None) == ""


def test_expansion_abreviation():
    assert normaliser_designation("LRP cicaplast", {"LRP": "LA ROCHE POSAY"}) == \
        "LA ROCHE POSAY CICAPLAST"


def test_extraire_dosage():
    assert extraire_dosage("CICAPLAST B5 200ML") == {"B5", "200ML"}


def test_dosages_concordants():
    assert dosages_concordants("DOLIPRANE 1000MG", "Doliprane 1000 mg") is True
    assert dosages_concordants("DOLIPRANE 1000MG", "DOLIPRANE 500MG") is False


def test_score_identique_vaut_1():
    assert score_designation("DOLIPRANE 1000MG", "doliprane 1000 mg") == 1.0


def test_score_proche_eleve():
    assert score_designation("ANTHELIOS 50 AGE CORRECT", "ANTHELIOS 50 AGE CORRECT PARFUM") >= 0.8


def test_score_eloigne_bas():
    assert score_designation("DOLIPRANE", "EFFERALGAN") < 0.5


def test_charger_abreviations(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    conn.execute("INSERT INTO abreviations_labo (abrev, complet) VALUES (?, ?)",
                 ("LRP", "LA ROCHE POSAY"))
    conn.commit()
    assert charger_abreviations(conn) == {"LRP": "LA ROCHE POSAY"}
