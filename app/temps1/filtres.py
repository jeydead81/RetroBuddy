from app.temps1.schemas import LigneFacture


def est_ligne_prix(ligne: LigneFacture) -> bool:
    """Ligne de prix au sens §3.2 : prix brut > 0, remise < 100 %, net > 0.

    Le rattachement à un identifiant (CIP/EAN ou code interne) est jugé par
    app.temps1.selection.qualifier_ligne, pas ici : une vraie ligne produit
    peut exister sans CIP (ex. factures AbbVie qui ne portent qu'un code interne).
    """
    if ligne.prix_brut is None or ligne.prix_brut <= 0:
        return False
    if ligne.remise_pct is not None and ligne.remise_pct >= 100:
        return False
    if ligne.prix_net is None or ligne.prix_net <= 0:
        return False
    return True
