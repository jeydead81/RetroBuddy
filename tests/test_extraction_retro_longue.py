import base64
import io

import pytest
from reportlab.pdfgen import canvas

from app.temps1.pdf_reader import PdfDocument
from app.temps1.pdf_split import decouper_pdf, nombre_pages
from app.temps2 import traitement_retro as tr
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne


def _pdf_n_pages(n):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(n):
        c.drawString(100, 700, f"page {i + 1}")
        c.showPage()
    c.save()
    octets = buf.getvalue()
    return PdfDocument(nom="t.pdf", base64=base64.b64encode(octets).decode("ascii"),
                       taille_octets=len(octets))


def test_decouper_pdf_reelle():
    pdf = _pdf_n_pages(5)
    assert nombre_pages(pdf) == 5
    morceaux = decouper_pdf(pdf, 2)
    assert [nombre_pages(m) for m in morceaux] == [2, 2, 1]   # 5 pages -> 2+2+1


class _FakeExtractor:
    """Renvoie (ou lève) le prochain élément de `resultats` à chaque appel."""
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


def _chunk(total=None, vent=None, lignes=()):
    return RetroExtrait(type_document="retrocession",
                        entete=RetroEntete(pharmacie_emettrice="SERALY",
                                           total_ht_affiche=total, ventilation=vent or []),
                        lignes=list(lignes))


def test_fusion_et_report_bl(monkeypatch):
    # 2 morceaux : le BL 'A' déborde du 1er au 2e (1re ligne du 2e sans en-tête BL).
    c1 = _chunk(lignes=[RetroLigne(designation="X1", bl_numero="A", bl_date="01/12/2025",
                                   montant_ht=10.0),
                        RetroLigne(designation="X2", bl_numero="A", bl_date="01/12/2025",
                                   montant_ht=20.0)])
    c2 = _chunk(total=130.0, vent=[{"taux": 20.0, "montant_ht": 130.0}],
                lignes=[RetroLigne(designation="X3", montant_ht=30.0),                  # continuation
                        RetroLigne(designation="X4", bl_numero="B", bl_date="02/12/2025",
                                   montant_ht=70.0)])
    ext = _FakeExtractor([c1, c2])
    monkeypatch.setattr(tr, "nombre_pages", lambda pdf: 20)          # > SEUIL -> découpe
    monkeypatch.setattr(tr, "decouper_pdf", lambda pdf, n: ["m1", "m2"])

    retro = tr.extraire_retro(ext, _pdf_n_pages(1), "m")
    assert [l.designation for l in retro.lignes] == ["X1", "X2", "X3", "X4"]
    assert (retro.lignes[2].bl_numero, retro.lignes[2].bl_date) == ("A", "01/12/2025")  # reporté
    assert retro.lignes[3].bl_numero == "B"
    assert retro.entete.total_ht_affiche == 130.0
    assert len(retro.entete.ventilation) == 1
    assert ext.dernier_cout == 1.0                                   # 2 appels × 0,5


def test_appel_unique_si_facture_courte(monkeypatch):
    monkeypatch.setattr(tr, "nombre_pages", lambda pdf: 3)           # <= SEUIL
    ext = _FakeExtractor([_chunk(total=50.0, lignes=[RetroLigne(designation="U")])])
    retro = tr.extraire_retro(ext, _pdf_n_pages(1), "m")
    assert ext.calls == 1                                            # pas de découpage
    assert len(retro.lignes) == 1


def test_fallback_decoupe_sur_troncature(monkeypatch):
    monkeypatch.setattr(tr, "nombre_pages", lambda pdf: 5)           # <= SEUIL -> tente 1 appel
    monkeypatch.setattr(tr, "decouper_pdf", lambda pdf, n: ["m1", "m2"])
    boom = ValueError("1 validation error for RetroExtrait Invalid JSON: EOF while parsing")
    ext = _FakeExtractor([boom, _chunk(lignes=[RetroLigne(designation="A")]),
                          _chunk(total=10.0, lignes=[RetroLigne(designation="B")])])
    retro = tr.extraire_retro(ext, _pdf_n_pages(1), "m")
    assert ext.calls == 3                                            # 1 raté + 2 morceaux
    assert [l.designation for l in retro.lignes] == ["A", "B"]


def test_erreur_non_troncature_propagee(monkeypatch):
    monkeypatch.setattr(tr, "nombre_pages", lambda pdf: 5)
    ext = _FakeExtractor([RuntimeError("authentication error: invalid x-api-key")])
    with pytest.raises(RuntimeError):
        tr.extraire_retro(ext, _pdf_n_pages(1), "m")
    assert ext.calls == 1                                            # pas de re-tentative en découpe
