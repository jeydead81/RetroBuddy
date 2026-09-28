from app.temps4.export_pdf import facture_pdf
from app.temps4.facture_builder import (
    Facture, GroupeBL, LigneFacturee, VentilationTva)


def _facture():
    ligne = LigneFacturee("PRODUIT A", "C1", 2, 6.0, 10.0, 5.0, 10.0, 10.0)
    return Facture(
        retro_id=1, emettrice="SERALY", destinataire="CENON", numero="N1",
        date_vente="22/09/2025",
        groupes=[GroupeBL("BL1", "01/08/2025", [ligne])],
        ventilation=[VentilationTva(10.0, 10.0, 1.0)],
        total_ht=10.0, total_tva=1.0, total_ttc=11.0, bloquee=False, n_rouge=0)


def test_pdf_renvoie_des_bytes_pdf():
    data = facture_pdf(_facture())
    assert isinstance(data, bytes)
    assert data[:4] == b"%PDF"


def _texte_pages(data):
    import io
    from pypdf import PdfReader
    return [p.extract_text() for p in PdfReader(io.BytesIO(data)).pages]


def _longue_facture():
    f = _facture()
    lignes = [LigneFacturee(f"PRODUIT {i}", f"C{i}", 1, 6.0, 10.0, 5.0, 10.0, 5.0)
              for i in range(250)]
    f.groupes = [GroupeBL("BL1", "01/08/2025", lignes)]
    f.mentions_emettrice = "EURL PHARMACIE SERALY\n48 Route de Chauvigny"
    f.destinataire_adresse = "1 place Michel Gaudineau\n86530 CENON SUR VIENNE\nFRANCE"
    return f


def test_pdf_numero_de_page_sur_chaque_page():
    pages = _texte_pages(facture_pdf(_longue_facture()))
    n = len(pages)
    assert n >= 2
    for i, t in enumerate(pages, 1):
        assert f"Page {i} / {n}" in t


def test_pdf_entete_fournisseur_client_sur_pages_suivantes():
    pages = _texte_pages(facture_pdf(_longue_facture()))
    for t in pages[1:]:
        assert "EURL PHARMACIE SERALY" in t
        assert "CENON" in t
        assert "N1" in t
        assert "1 place Michel Gaudineau, 86530 CENON SUR VIENNE, FRANCE" in t


def test_pdf_client_en_haut_a_droite_page_1():
    import io
    from pypdf import PdfReader
    page = PdfReader(io.BytesIO(facture_pdf(_longue_facture()))).pages[0]
    pos = {}

    def visiteur(texte, cm, tm, font, size):
        if texte.strip():
            pos.setdefault(texte.strip(), cm[4] + tm[4])

    page.extract_text(visitor_text=visiteur)
    x_client = next(x for t, x in pos.items() if "CENON" in t)
    x_emet = next(x for t, x in pos.items() if "SERALY" in t)
    assert x_client > x_emet + 50          # colonne de droite
