from dataclasses import dataclass

from app.codes.checksum import type_de_code
from app.temps1 import filtres
from app.temps1.schemas import LigneFacture


@dataclass
class Qualification:
    inclure: bool          # la ligne entre-t-elle au référentiel ?
    code_ref: str | None   # clé de stockage : CIP/EAN, ou code interne
    type_code: str | None  # 'CIP13' | 'EAN13' | 'interne' | 'inconnu' | None
    note: str | None       # raison d'exclusion, ou note (« sans CIP… »)


def qualifier_ligne(ligne: LigneFacture) -> Qualification:
    """Décide si une ligne entre au référentiel et sous quelle clé (Option A).

    - CIP13 / EAN13 valide      -> incluse, clé = le code, type CIP13/EAN13.
    - prix mais pas de CIP       -> incluse, clé = code interne, type 'interne'
                                    (rapprochement par désignation au Temps 2).
    - code 13 chiffres clé KO    -> exclue (suspect : CIP probablement mal lu).
    - ni prix, ni identifiant     -> exclue.
    """
    if not filtres.est_ligne_prix(ligne):
        return Qualification(False, None, None,
                             "ligne non-prix (UG / RFA / remise globale)")

    t = type_de_code(ligne.code)
    if t in ("CIP13", "EAN13"):
        return Qualification(True, str(ligne.code).strip(), t, None)

    code_brut = str(ligne.code).strip() if ligne.code else ""
    if code_brut.isdigit() and len(code_brut) == 13:
        return Qualification(False, None, "inconnu",
                             "code 13 chiffres invalide (checksum) — à vérifier")

    interne = ligne.code_interne or ligne.code
    interne = str(interne).strip() if interne else ""
    if interne:
        return Qualification(True, interne, "interne",
                             "sans CIP — rapprochement par désignation")

    return Qualification(False, None, None, "aucun identifiant — à compléter")
