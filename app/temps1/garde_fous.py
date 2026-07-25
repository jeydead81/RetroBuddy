from app.codes.checksum import type_de_code
from app.temps1.schemas import LigneFacture


def checksum_ok(ligne: LigneFacture) -> bool:
    """Vrai si le code porté par la ligne est un CIP13 ou EAN13 valide."""
    return type_de_code(ligne.code) in ("CIP13", "EAN13")


def reconcilier_totaux(lignes, total_affiche, deductions_pied=0.0, seuil_pct=1.0, seuil_abs=0.02):
    """Compare la somme des montants HT extraits au total HT affiché.

    `total_affiche` = Net HT à payer (APRÈS déductions de pied de facture). `deductions_pied`
    = somme des déductions de pied (escompte, avoir, remise globale, reprise périmés, op
    commerciale…). Le contrôle exact est donc : Σ montant_ht lignes == total_affiche +
    deductions_pied. Ça tolère n'importe quelle déduction de pied SANS lister les libellés,
    tout en gardant la détection d'une ligne oubliée ou mal lue (l'égalité casse).

    Retourne (ok, total_calcule). La somme couvre TOUTES les lignes extraites.
    """
    total_calcule = sum(l.montant_ht for l in lignes if l.montant_ht is not None)
    if total_affiche is None:
        return (False, total_calcule)
    cible = total_affiche + (deductions_pied or 0.0)
    ecart = abs(total_calcule - cible)
    tolere = max(seuil_abs, abs(total_affiche) * seuil_pct / 100)
    return (ecart <= tolere, total_calcule)
