from app.db import get_connection, init_db
from app.temps1.extraction_ia import MockExtractor
from app.temps1.pdf_reader import PdfDocument
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne
from app.temps2.traitement_retro import traiter_retro

CFG = {"model_defaut": "claude-sonnet-4-6", "model_escalade": "claude-opus-4-8",
       "seuil_match_bas": 0.80, "seuil_match_auto": 0.95}


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code, date_facture, prix_net, designation):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_brut, remise_pct, prix_net, designation) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (code, date_facture, prix_net + 1, 10.0, prix_net, designation))
    conn.commit()


def _pdf():
    return PdfDocument(nom="retro.pdf", base64="", taille_octets=0)


def _retro(lignes):
    return RetroExtrait(type_document="retro_lgo",
                        entete=RetroEntete(pharmacie_emettrice="A", pharmacie_destinataire="B"),
                        lignes=lignes)


def _ligne(code, designation, bl_date="10/08/2025"):
    return RetroLigne(designation=designation, code=code, type_code="CIP13", qte=1,
                      tva=10.0, bl_numero="BL1", bl_date=bl_date)


def test_orange_par_designation_autovalide(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930156421", "01/08/2025", 4.5, "REXORUBIA GLE 350G")
    retro = _retro([_ligne("9999999999999", "REXORUBIA GLE 350 G")])  # code LGO introuvable
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_orange == 1
    r = conn.execute("SELECT statut_ecart, code_resolu, prix_net, passe_match, "
                     "score_match, valide_utilisateur FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "orange"
    assert r["code_resolu"] == "3400930156421"
    assert r["prix_net"] == 4.5
    assert r["passe_match"] in (3, 4)
    assert r["score_match"] >= 0.95
    assert r["valide_utilisateur"] == 1


def test_orange_a_confirmer_si_dosage_discordant(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C1", "01/08/2025", 4.5, "DOLIPRANE 500MG")
    retro = _retro([_ligne("9999999999999", "DOLIPRANE 1000MG")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_rouge == 1


def test_priorite_code_sur_designation(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400937882248", "01/08/2025", 2.0, "IMODIUMDUO CPR 12")
    retro = _retro([_ligne("3400937882248", "AUTRE DESIGNATION")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_resolu == 1
    r = conn.execute("SELECT statut_ecart, passe_match FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "resolu"
    assert r["passe_match"] == 1
