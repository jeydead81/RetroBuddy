from app.db import get_connection, init_db
from app.temps1.extraction_ia import MockExtractor
from app.temps1.pdf_reader import PdfDocument
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne
from app.temps2.traitement_retro import traiter_retro

CFG = {"model_defaut": "claude-sonnet-4-6", "model_escalade": "claude-opus-4-8"}


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code, date_facture, prix_net):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_brut, remise_pct, prix_net) "
        "VALUES (?, ?, ?, ?, ?)",
        (code, date_facture, prix_net + 1, 10.0, prix_net))
    conn.commit()


def _pdf():
    return PdfDocument(nom="retro.pdf", base64="", taille_octets=0)


def _retro(lignes, total=None):
    # Par défaut le total affiché = Σ des montants de ligne -> réconcilie (pas d'escalade).
    if total is None:
        total = round(sum((l.montant_ht or 0) for l in lignes), 2)
    return RetroExtrait(
        type_document="retro_lgo",
        entete=RetroEntete(pharmacie_emettrice="SERALY",
                           pharmacie_destinataire="CENON",
                           date_vente="22/09/2025", numero="N1",
                           total_ht_affiche=total),
        lignes=lignes)


def _ligne(code, bl_date, bl_numero="28476", montant_ht=10.0):
    return RetroLigne(designation="X", code=code, type_code="CIP13", qte=1,
                      tva=10.0, bl_numero=bl_numero, bl_date=bl_date, montant_ht=montant_ht)


def test_ligne_resolue(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007", "01/08/2025", 4.5)
    retro = _retro([_ligne("3400930000007", "10/08/2025")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_resolu == 1
    assert res.n_rouge == 0
    r = conn.execute("SELECT statut_ecart, prix_net, code_resolu, passe_match "
                     "FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "resolu"
    assert r["prix_net"] == 4.5
    assert r["code_resolu"] == "3400930000007"
    assert r["passe_match"] == 1


def test_ligne_rouge_code_absent(tmp_path):
    conn = _conn(tmp_path)
    retro = _retro([_ligne("3400930000007", "10/08/2025")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_rouge == 1
    r = conn.execute("SELECT statut_ecart, prix_net FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "rouge"
    assert r["prix_net"] is None


def test_ligne_rouge_prix_posterieur_au_bl(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007", "20/08/2025", 4.5)   # prix APRÈS le BL
    retro = _retro([_ligne("3400930000007", "10/08/2025")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_rouge == 1
    assert conn.execute("SELECT statut_ecart FROM retro_lignes").fetchone()["statut_ecart"] == "rouge"


def test_multi_bl_meme_produit_deux_prix(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007", "01/07/2025", 5.0)
    _ref(conn, "3400930000007", "05/08/2025", 4.5)
    retro = _retro([
        _ligne("3400930000007", "15/07/2025", bl_numero="A"),   # -> 5.0
        _ligne("3400930000007", "10/08/2025", bl_numero="B"),   # -> 4.5
    ])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_resolu == 2
    prix = [r["prix_net"] for r in conn.execute(
        "SELECT prix_net FROM retro_lignes ORDER BY bl_numero")]
    assert prix == [5.0, 4.5]


class _ExtracteurAvecCout:
    def __init__(self, retro, cout):
        self._retro = retro
        self.dernier_cout = cout

    def extraire(self, pdf, model):
        return self._retro


def test_cout_remonte(tmp_path):
    conn = _conn(tmp_path)
    retro = _retro([_ligne("3400930000007", "10/08/2025")])
    res = traiter_retro(conn, _pdf(), _ExtracteurAvecCout(retro, 0.04), CFG)
    assert res.cout == 0.04
    c = conn.execute("SELECT cout_estime FROM retro_documents").fetchone()["cout_estime"]
    assert c == 0.04


# --- Garde-fou de complétude : réconciliation du Total HT + escalade Opus ---

def test_reconciliation_ok_enregistree(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007", "01/08/2025", 4.5)
    retro = _retro([_ligne("3400930000007", "10/08/2025")])    # total 10 = Σ montants
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.reconciliation_ok is True
    d = conn.execute("SELECT reconciliation_ok, total_ht_calcule FROM retro_documents").fetchone()
    assert d["reconciliation_ok"] == 1
    assert d["total_ht_calcule"] == 10.0


def test_reconciliation_escalade_opus_corrige(tmp_path):
    conn = _conn(tmp_path)
    mauvais = _retro([_ligne("3400930000007", "10/08/2025")], total=999.0)   # Sonnet : ne colle pas
    bon = _retro([_ligne("3400930000007", "10/08/2025")])                    # Opus : réconcilie
    ex = MockExtractor(par_modele={"claude-sonnet-4-6": mauvais, "claude-opus-4-8": bon})
    res = traiter_retro(conn, _pdf(), ex, CFG)
    assert res.reconciliation_ok is True
    assert ("retro.pdf", "claude-opus-4-8") in ex.appels       # escalade bien déclenchée
    assert conn.execute("SELECT reconciliation_ok FROM retro_documents").fetchone()[0] == 1


def test_reconciliation_echec_bloque_la_facture(tmp_path):
    from app.temps4.facture_builder import construire_facture
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007", "01/08/2025", 4.5)             # la ligne se résout (0 rouge)
    mauvais = _retro([_ligne("3400930000007", "10/08/2025")], total=999.0)
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=mauvais), CFG)
    assert res.reconciliation_ok is False
    assert res.n_rouge == 0
    f = construire_facture(conn, res.retro_id)
    assert f.reconciliation_ok is False
    assert f.bloquee is True                                   # bloquée sans aucune ligne rouge
