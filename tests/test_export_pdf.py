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
