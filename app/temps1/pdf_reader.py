import base64
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PdfDocument:
    nom: str
    base64: str
    taille_octets: int


def lire_pdf(chemin) -> PdfDocument:
    p = Path(chemin)
    octets = p.read_bytes()
    return PdfDocument(
        nom=p.name,
        base64=base64.standard_b64encode(octets).decode("ascii"),
        taille_octets=len(octets),
    )
