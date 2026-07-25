import base64
import io

import pytest
from reportlab.pdfgen import canvas

from app.temps1 import pipeline as pl
from app.temps1.pdf_reader import PdfDocument
from app.temps1.schemas import EnteteFacture, FactureExtraite, LigneFacture


def _pdf_n_pages(n):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(n):
        c.drawString(100, 700, f"p{i + 1}")
        c.showPage()
    c.save()
    o = buf.getvalue()
    return PdfDocument(nom="t.pdf", base64=base64.b64encode(o).decode("ascii"),
                       taille_octets=len(o))


class _FakeExtractor:
    def __init__(self, resultats):
        self.resultats = list(resultats)
        self.dernier_cout = 0.0
        self.calls = 0

    def extraire(self, pdf, model):
        self.calls += 1
        self.dernier_cout = 0.5
        r = self.resultats.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _chunk(total=None, ded=0.0, lignes=(), type_doc="facture_marchandise"):
    return FactureExtraite(
        type_document=type_doc,
        entete=EnteteFacture(labo="LABO", total_ht_affiche=total, deductions_pied=ded),
        lignes=list(lignes))


def _l(net, montant):
    return LigneFacture(code="3400930000007", designation="X", qte=1, prix_brut=net + 1,
                        remise_pct=10.0, prix_net=net, montant_ht=montant, tva=20.0)


def test_fusion_labo(monkeypatch):
    c1 = _chunk(lignes=[_l(10, 10), _l(20, 20)])                    # pas de récap
    c2 = _chunk(total=25.0, ded=5.0, lignes=[_l(30, 30)])           # récap (total + déductions)
    ext = _FakeExtractor([c1, c2])
    monkeypatch.setattr(pl, "nombre_pages", lambda pdf: 20)         # > SEUIL -> découpe
    monkeypatch.setattr(pl, "decouper_pdf", lambda pdf, n: ["m1", "m2"])
    f = pl.extraire_facture(ext, _pdf_n_pages(1), "m")
    assert len(f.lignes) == 3
    assert f.entete.total_ht_affiche == 25.0
    assert f.entete.deductions_pied == 5.0
    assert f.type_document == "facture_marchandise"
    assert ext.dernier_cout == 1.0                                  # 2 appels × 0,5


def test_appel_unique_labo(monkeypatch):
    monkeypatch.setattr(pl, "nombre_pages", lambda pdf: 3)          # <= SEUIL
    ext = _FakeExtractor([_chunk(total=10.0, lignes=[_l(10, 10)])])
    f = pl.extraire_facture(ext, _pdf_n_pages(1), "m")
    assert ext.calls == 1 and len(f.lignes) == 1


def test_fallback_troncature_labo(monkeypatch):
    monkeypatch.setattr(pl, "nombre_pages", lambda pdf: 5)          # <= SEUIL -> tente 1 appel
    monkeypatch.setattr(pl, "decouper_pdf", lambda pdf, n: ["m1", "m2"])
    boom = ValueError("1 validation error Invalid JSON: EOF while parsing")
    ext = _FakeExtractor([boom, _chunk(lignes=[_l(1, 1)]),
                          _chunk(total=2.0, lignes=[_l(1, 1)])])
    f = pl.extraire_facture(ext, _pdf_n_pages(1), "m")
    assert ext.calls == 3 and len(f.lignes) == 2                    # 1 raté + 2 morceaux


def test_erreur_non_troncature_propagee_labo(monkeypatch):
    monkeypatch.setattr(pl, "nombre_pages", lambda pdf: 5)
    ext = _FakeExtractor([RuntimeError("authentication error: invalid x-api-key")])
    with pytest.raises(RuntimeError):
        pl.extraire_facture(ext, _pdf_n_pages(1), "m")
    assert ext.calls == 1                                           # pas de re-tentative
