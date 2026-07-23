import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import creer_app, get_extractor
from app.temps1.extraction_lot import (EscaladeDifferee, ExtracteurPreExtrait,
                                       attendre_lots, resultats_lots, soumettre_lots)
from app.temps1.schemas import EnteteFacture, FactureExtraite, LigneFacture

# ---------------------------------------------------------------- faux client

def _facture_json(total=10.0):
    return FactureExtraite(
        type_document="facture_marchandise",
        entete=EnteteFacture(labo="URGO", numero_facture="F1",
                             date_facture="10/01/2026", total_ht_affiche=total),
        lignes=[LigneFacture(code="3400930000007", designation="X", qte=2,
                             prix_brut=6.0, remise_pct=10.0, prix_net=5.0,
                             montant_ht=10.0)]).model_dump_json()


class FauxBatches:
    """Simule client.messages.batches : reponses(custom_id, model) -> texte JSON."""

    def __init__(self, reponses):
        self._reponses = reponses
        self._lots = {}
        self.creations = []

    def create(self, requests):
        lot_id = f"lot_{len(self._lots)}"
        self._lots[lot_id] = requests
        self.creations.append(requests)
        return SimpleNamespace(id=lot_id)

    def retrieve(self, lot_id):
        n = len(self._lots[lot_id])
        return SimpleNamespace(
            processing_status="ended",
            request_counts=SimpleNamespace(succeeded=n, errored=0, canceled=0, expired=0))

    def results(self, lot_id):
        for req in self._lots[lot_id]:
            cid, modele = req["custom_id"], req["params"]["model"]
            texte = self._reponses(cid, modele)
            usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0,
                                    cache_read_input_tokens=0, cache_creation_input_tokens=0)
            yield SimpleNamespace(custom_id=cid, result=SimpleNamespace(
                type="succeeded",
                message=SimpleNamespace(stop_reason="end_turn", usage=usage,
                                        content=[SimpleNamespace(type="text", text=texte)])))


class FauxClient:
    def __init__(self, reponses):
        self.messages = SimpleNamespace(batches=FauxBatches(reponses))

    def with_options(self, **kw):
        return self


# ---------------------------------------------------------------- tests unitaires

def _fichiers_pdf(tmp_path, n, taille=100):
    paires = []
    for i in range(n):
        p = tmp_path / f"f{i}.pdf"
        p.write_bytes(b"%PDF " + bytes([65 + i % 26]) * taille)
        paires.append((str(i), str(p)))
    return paires


def test_decoupage_en_sous_lots(tmp_path, monkeypatch):
    import app.temps1.extraction_lot as lot
    monkeypatch.setattr(lot, "MAX_REQUETES_SOUS_LOT", 2)     # force le découpage
    client = FauxClient(lambda cid, m: _facture_json())
    ids = soumettre_lots(client, "claude-sonnet-4-6", "p", FactureExtraite,
                         _fichiers_pdf(tmp_path, 5))
    assert len(ids) == 3                                      # 2 + 2 + 1
    assert sum(len(c) for c in client.messages.batches.creations) == 5


def test_roundtrip_et_cout_moitie_prix(tmp_path):
    client = FauxClient(lambda cid, m: _facture_json())
    ids = soumettre_lots(client, "claude-sonnet-4-6", "p", FactureExtraite,
                         _fichiers_pdf(tmp_path, 2))
    attendre_lots(client, ids, intervalle=0)
    res = list(resultats_lots(client, ids, "claude-sonnet-4-6", FactureExtraite))
    assert len(res) == 2
    for cle, ok, facture, cout in res:
        assert ok and facture.entete.labo == "URGO"
        # 1M tokens input Sonnet = 3 $ = 2,76 € plein tarif -> 1,38 € en lot (-50 %)
        assert cout == pytest.approx(2.76 * 0.5)


def test_resultat_illisible_en_erreur(tmp_path):
    client = FauxClient(lambda cid, m: "pas du json")
    ids = soumettre_lots(client, "claude-sonnet-4-6", "p", FactureExtraite,
                         _fichiers_pdf(tmp_path, 1))
    attendre_lots(client, ids, intervalle=0)
    (cle, ok, motif, cout), = resultats_lots(client, ids, "claude-sonnet-4-6", FactureExtraite)
    assert not ok
    assert "schéma" in motif


def test_extracteur_pre_extrait_escalade():
    pre = ExtracteurPreExtrait({"claude-sonnet-4-6": ("F", 0.1)})
    assert pre.extraire(None, "claude-sonnet-4-6") == "F"
    assert pre.dernier_cout == 0.1
    with pytest.raises(EscaladeDifferee):
        pre.extraire(None, "claude-opus-4-8")


# ---------------------------------------------------------------- bout en bout

class FauxExtracteurLot:
    """Ressemble à ClaudeExtractor (attributs client/prompt) mais 100 % local."""

    def __init__(self, reponses):
        self.client = FauxClient(reponses)
        self.prompt = "prompt de test"


def _attendre_job(client_http, job_id, timeout=10):
    debut = time.monotonic()
    while time.monotonic() - debut < timeout:
        j = client_http.get(f"/ingest/progress/{job_id}").json()
        if j.get("termine"):
            return j
        time.sleep(0.05)
    raise AssertionError("job non terminé")


def test_job_lot_complet_avec_escalade(tmp_path):
    # 12 fichiers (>= seuil lot). Le fichier n°3 : Sonnet renvoie un total faux
    # -> escalade -> Opus renvoie un total juste -> ingéré quand même.
    def reponses(cid, modele):
        if cid == "3" and modele == "claude-sonnet-4-6":
            return _facture_json(total=999.0)                # ne réconcilie pas
        return _facture_json(total=10.0)

    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_extractor] = lambda: FauxExtracteurLot(reponses)
    client = TestClient(app)

    fichiers = [("fichiers", (f"f{i}.pdf", b"%PDF batch " + str(i).encode(), "application/pdf"))
                for i in range(12)]
    r = client.post("/ingest/start", files=fichiers)
    j = _attendre_job(client, r.json()["job_id"])

    assert j["total"] == 12 and j["fait"] == 12
    statuts = {d["fichier"]: d["statut"] for d in j["details"]}
    assert all(s == "ingeree" for s in statuts.values())
    c = get_connection(str(tmp_path / "web.db"))
    assert c.execute("SELECT COUNT(*) n FROM factures").fetchone()["n"] == 12
    # l'escaladée a bien été extraite par Opus (2e lot)
    modeles = {r["fichier"]: r["modele_extraction"] for r in c.execute(
        "SELECT fichier, modele_extraction FROM factures")}
    assert modeles["f3.pdf"] == "claude-opus-4-8"
    assert sum(1 for m in modeles.values() if m == "claude-opus-4-8") == 1
    # empreintes stockées -> un ré-import serait dédupliqué
    assert c.execute("SELECT COUNT(*) n FROM factures WHERE empreinte IS NOT NULL"
                     ).fetchone()["n"] == 12


def test_job_lot_dedup_zero_cout(tmp_path):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_extractor] = lambda: FauxExtracteurLot(
        lambda cid, m: _facture_json())
    client = TestClient(app)
    contenu = [(f"f{i}.pdf", b"%PDF dup " + str(i).encode()) for i in range(12)]
    fichiers = [("fichiers", (n, b, "application/pdf")) for n, b in contenu]
    j1 = _attendre_job(client, client.post("/ingest/start", files=fichiers).json()["job_id"])
    assert j1["cout"] > 0
    # ré-import du MÊME lot : tout dédupliqué, coût 0
    j2 = _attendre_job(client, client.post("/ingest/start", files=fichiers).json()["job_id"])
    assert j2["fait"] == 12
    assert j2["cout"] == 0.0
    assert all(d["statut"] == "ignoree" for d in j2["details"])
