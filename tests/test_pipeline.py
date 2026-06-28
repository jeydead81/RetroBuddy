from app.db import get_connection, init_db
from app.temps1.extraction_ia import MockExtractor
from app.temps1.pdf_reader import PdfDocument
from app.temps1.pipeline import traiter_facture
from app.temps1.schemas import EnteteFacture, FactureExtraite, LigneFacture

CFG = {"model_defaut": "claude-sonnet-4-6", "model_escalade": "claude-opus-4-8",
       "seuil_reconciliation_pct": 1.0}


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _pdf():
    return PdfDocument(nom="f.pdf", base64="", taille_octets=0)


def _facture(type_document="facture_marchandise", lignes=None, total=None):
    return FactureExtraite(
        type_document=type_document,
        entete=EnteteFacture(labo="URGO", numero_facture="F1",
                             date_facture="2026-01-10", total_ht_affiche=total),
        lignes=lignes or [],
    )


def _ligne(code="3400930000007", net=5.0, montant=10.0, code_interne=None):
    return LigneFacture(code=code, code_interne=code_interne, designation="X",
                        prix_brut=6.0, remise_pct=10.0, prix_net=net, montant_ht=montant)


def test_facture_nominale_ingeree(tmp_path):
    conn = _conn(tmp_path)
    f = _facture(lignes=[_ligne(montant=10.0)], total=10.0)
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "ingeree"
    assert res.n_referentiel == 1
    n = conn.execute("SELECT COUNT(*) c FROM referentiel_prix").fetchone()["c"]
    assert n == 1


def test_avoir_ignore(tmp_path):
    conn = _conn(tmp_path)
    f = _facture(type_document="avoir")
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "ignoree"
    assert conn.execute("SELECT COUNT(*) c FROM referentiel_prix").fetchone()["c"] == 0


def test_totaux_non_reconcilies_en_revue(tmp_path):
    conn = _conn(tmp_path)
    f = _facture(lignes=[_ligne(montant=10.0)], total=99.0)
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "en_revue"
    assert conn.execute("SELECT COUNT(*) c FROM referentiel_prix").fetchone()["c"] == 0


def test_escalade_opus_recupere(tmp_path):
    conn = _conn(tmp_path)
    sonnet = _facture(lignes=[_ligne(montant=10.0)], total=99.0)   # ne réconcilie pas
    opus = _facture(lignes=[_ligne(montant=10.0)], total=10.0)     # réconcilie
    ex = MockExtractor(par_modele={"claude-sonnet-4-6": sonnet, "claude-opus-4-8": opus})
    res = traiter_facture(conn, _pdf(), ex, CFG)
    assert res.statut == "ingeree"
    assert ex.appels == [("f.pdf", "claude-sonnet-4-6"), ("f.pdf", "claude-opus-4-8")]
    fid = res.facture_id
    modele = conn.execute("SELECT modele_extraction FROM factures WHERE id=?", (fid,)).fetchone()
    assert modele["modele_extraction"] == "claude-opus-4-8"


def test_abonnement_avec_lignes_produit_passe_en_revue(tmp_path):
    # Cas Alloga : marchandise parapharma mal classée "abonnement_service" par les DEUX
    # modèles -> ne doit PAS être ignorée en silence, mais signalée "en revue".
    conn = _conn(tmp_path)
    f = _facture(type_document="abonnement_service",
                 lignes=[_ligne(montant=10.0)], total=10.0)
    ex = MockExtractor(par_modele={"claude-sonnet-4-6": f, "claude-opus-4-8": f})
    res = traiter_facture(conn, _pdf(), ex, CFG)
    assert res.statut == "en_revue"                                  # jamais "ignoree"
    assert ex.appels == [("f.pdf", "claude-sonnet-4-6"), ("f.pdf", "claude-opus-4-8")]
    assert conn.execute("SELECT COUNT(*) c FROM referentiel_prix").fetchone()["c"] == 0
    motif = conn.execute("SELECT motif FROM factures").fetchone()["motif"]
    assert "ligne" in motif                                          # motif explicite


def test_abonnement_mal_classe_recupere_par_opus(tmp_path):
    # Sonnet se trompe ("abonnement"), Opus rectifie ("facture_marchandise") -> ingérée.
    conn = _conn(tmp_path)
    sonnet = _facture(type_document="abonnement_service",
                      lignes=[_ligne(montant=10.0)], total=10.0)
    opus = _facture(type_document="facture_marchandise",
                    lignes=[_ligne(montant=10.0)], total=10.0)
    ex = MockExtractor(par_modele={"claude-sonnet-4-6": sonnet, "claude-opus-4-8": opus})
    res = traiter_facture(conn, _pdf(), ex, CFG)
    assert res.statut == "ingeree"
    assert res.n_referentiel == 1
    assert ex.appels[-1] == ("f.pdf", "claude-opus-4-8")


def test_vrai_abonnement_sans_lignes_reste_ignore(tmp_path):
    # Vrai abonnement (aucune ligne produit) -> ignoré, SANS escalade Opus inutile.
    conn = _conn(tmp_path)
    f = _facture(type_document="abonnement_service", lignes=[], total=50.0)
    ex = MockExtractor(defaut=f)
    res = traiter_facture(conn, _pdf(), ex, CFG)
    assert res.statut == "ignoree"
    assert ex.appels == [("f.pdf", "claude-sonnet-4-6")]             # pas d'escalade


def test_ligne_checksum_invalide_exclue_du_referentiel(tmp_path):
    conn = _conn(tmp_path)
    # code 13 chiffres à clé invalide → ligne flaggée (suspect), hors référentiel,
    # mais total réconcilie donc facture ingérée.
    f = _facture(lignes=[_ligne(code="3400930000000", montant=10.0)], total=10.0)
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "ingeree"
    assert res.n_referentiel == 0
    ligne = conn.execute("SELECT checksum_ok, valide FROM lignes_facture").fetchone()
    assert ligne["checksum_ok"] == 0
    assert ligne["valide"] == 0


def test_ligne_sans_cip_stockee_comme_interne(tmp_path):
    conn = _conn(tmp_path)
    # Cas AbbVie : prix correct, pas de CIP, seul un code interne.
    f = _facture(lignes=[_ligne(code=None, code_interne="20007519", montant=10.0)], total=10.0)
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "ingeree"
    assert res.n_referentiel == 1
    r = conn.execute("SELECT code, type_code, labo FROM referentiel_prix").fetchone()
    assert r["code"] == "20007519"
    assert r["type_code"] == "interne"
    assert r["labo"] == "URGO"
    lf = conn.execute("SELECT valide, motif_ligne FROM lignes_facture").fetchone()
    assert lf["valide"] == 1
    assert "CIP" in lf["motif_ligne"]


def test_ligne_sans_aucun_identifiant_exclue(tmp_path):
    conn = _conn(tmp_path)
    f = _facture(lignes=[_ligne(code=None, code_interne=None, montant=10.0)], total=10.0)
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "ingeree"
    assert res.n_referentiel == 0
    lf = conn.execute("SELECT valide FROM lignes_facture").fetchone()
    assert lf["valide"] == 0


class _ExtracteurAvecCout:
    def __init__(self, facture, cout):
        self._facture = facture
        self.dernier_cout = cout

    def extraire(self, pdf, model):
        return self._facture


def test_cout_remonte_dans_resultat_et_persiste(tmp_path):
    conn = _conn(tmp_path)
    f = _facture(lignes=[_ligne(montant=10.0)], total=10.0)
    res = traiter_facture(conn, _pdf(), _ExtracteurAvecCout(f, 0.025), CFG)
    assert res.cout == 0.025
    c = conn.execute("SELECT cout_estime FROM factures").fetchone()["cout_estime"]
    assert c == 0.025


def test_cout_avec_mock_est_nul(tmp_path):
    conn = _conn(tmp_path)
    f = _facture(lignes=[_ligne(montant=10.0)], total=10.0)
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.cout == 0.0
