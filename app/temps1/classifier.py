from app.temps1.schemas import FactureExtraite

TYPES_A_TRAITER = {"facture_marchandise"}

MOTIFS = {
    "avoir": "avoir (exclu du référentiel)",
    "abonnement_service": "abonnement / prestation",
    "releve": "relevé d'échéances",
    "autre": "document non traité en V1",
}


def decision(facture: FactureExtraite):
    """Retourne ('traiter', None) ou ('ignorer', motif)."""
    t = facture.type_document
    if t in TYPES_A_TRAITER:
        return ("traiter", None)
    return ("ignorer", MOTIFS.get(t, f"type non traité: {t}"))
