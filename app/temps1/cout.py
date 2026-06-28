# Tarifs $ par million de tokens (input, output). Source : skill claude-api.
PRIX_PAR_MTOK = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}

# Conversion approximative $ -> € (les coûts affichés sont purement indicatifs).
TAUX_USD_EUR = 0.92


def cout_appel(model, usage) -> float:
    """Coût € (approximatif) d'un appel d'extraction, à partir de l'`usage` de l'API.

    Calculé en $ via `PRIX_PAR_MTOK` puis converti en € via `TAUX_USD_EUR`.
    `input_tokens` = portion non cachée (plein tarif). Cache lu ≈ ×0,1,
    cache écrit ≈ ×1,25. Modèle inconnu → 0 (pas de tarif connu).
    """
    prix_in, prix_out = PRIX_PAR_MTOK.get(model, (0.0, 0.0))
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cout_in = (inp + cache_read * 0.1 + cache_write * 1.25) * prix_in / 1_000_000
    cout_out = out * prix_out / 1_000_000
    return (cout_in + cout_out) * TAUX_USD_EUR
