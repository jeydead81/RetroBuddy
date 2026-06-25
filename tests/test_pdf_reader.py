import base64

from app.temps1.pdf_reader import lire_pdf


def test_lire_pdf_encode_base64(tmp_path):
    contenu = b"%PDF-1.4 fake bytes"
    f = tmp_path / "facture.pdf"
    f.write_bytes(contenu)

    doc = lire_pdf(f)

    assert doc.nom == "facture.pdf"
    assert doc.taille_octets == len(contenu)
    assert base64.standard_b64decode(doc.base64) == contenu
