from app.temps1.schemas import LigneFacture


def ligne_valide(ligne: LigneFacture) -> bool:
    """Règles §3.2 : prix brut > 0, remise < 100 %, net > 0, code rattaché."""
    if ligne.code is None or not str(ligne.code).strip():
        return False
    if ligne.prix_brut is None or ligne.prix_brut <= 0:
        return False
    if ligne.remise_pct is not None and ligne.remise_pct >= 100:
        return False
    if ligne.prix_net is None or ligne.prix_net <= 0:
        return False
    return True
