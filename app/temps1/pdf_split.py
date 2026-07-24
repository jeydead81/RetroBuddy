import base64
import io

from pypdf import PdfReader, PdfWriter

from app.temps1.pdf_reader import PdfDocument


def nombre_pages(pdf: PdfDocument) -> int:
    """Nombre de pages du PDF. 0 si illisible ici (base64 vide/invalide) : l'appelant
    tentera alors un extraction en un seul appel, qui échouera proprement si besoin."""
    try:
        return len(PdfReader(io.BytesIO(base64.b64decode(pdf.base64 or ""))).pages)
    except Exception:
        return 0


def decouper_pdf(pdf: PdfDocument, pages_par_lot: int):
    """Découpe un PDF en sous-PDF de `pages_par_lot` pages consécutives.

    Sert à extraire une facture trop longue pour un seul appel (plafond de tokens) :
    on découpe, on extrait chaque morceau, puis on fusionne les lignes. Retourne une
    liste de PdfDocument dans l'ordre des pages."""
    data = base64.b64decode(pdf.base64)
    reader = PdfReader(io.BytesIO(data))
    n = len(reader.pages)
    morceaux = []
    for debut in range(0, n, pages_par_lot):
        fin = min(debut + pages_par_lot, n)
        writer = PdfWriter()
        for i in range(debut, fin):
            writer.add_page(reader.pages[i])
        buf = io.BytesIO()
        writer.write(buf)
        octets = buf.getvalue()
        morceaux.append(PdfDocument(
            nom=f"{pdf.nom}#p{debut + 1}-{fin}",
            base64=base64.b64encode(octets).decode("ascii"),
            taille_octets=len(octets)))
    return morceaux
