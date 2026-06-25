from app.codes.checksum import type_de_code
from app.temps1.schemas import LigneFacture


def checksum_ok(ligne: LigneFacture) -> bool:
    """Vrai si le code porté par la ligne est un CIP13 ou EAN13 valide."""
    return type_de_code(ligne.code) in ("CIP13", "EAN13")


def reconcilier_totaux(lignes, total_affiche, seuil_pct=1.0, seuil_abs=0.02):
    """Compare la somme des montants HT extraits au total HT affiché.

    Retourne (ok, total_calcule). La somme couvre TOUTES les lignes extraites
    (validation de l'extraction), indépendamment des filtres §3.2.
    """
    total_calcule = sum(l.montant_ht for l in lignes if l.montant_ht is not None)
    if total_affiche is None:
        return (False, total_calcule)
    ecart = abs(total_calcule - total_affiche)
    tolere = max(seuil_abs, abs(total_affiche) * seuil_pct / 100)
    return (ecart <= tolere, total_calcule)
