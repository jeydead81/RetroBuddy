def fmt_qte(v):
    """Quantité sans décimale superflue (produits indivisibles) : 3.0 -> '3'.

    Conserve une éventuelle fraction réelle (2.5 -> '2.5'), gère None -> ''.
    """
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else f"{f:g}"
