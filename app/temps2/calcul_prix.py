from app.temps2.normalisation_dates import normaliser_date


def prix_a_date(conn, code_resolu, bl_date):
    """Dernier prix net du référentiel pour `code_resolu` avec date_facture <= bl_date.

    Comparaison en Python (dates du référentiel en texte, formats variés).
    Retourne un dict {date_facture, prix_brut, remise_pct, prix_net} ou None.
    """
    d_bl = normaliser_date(bl_date)
    if d_bl is None or not code_resolu:
        return None
    rows = conn.execute(
        "SELECT date_facture, prix_brut, remise_pct, prix_net "
        "FROM referentiel_prix WHERE code = ?",
        (code_resolu,),
    ).fetchall()
    candidats = []
    for r in rows:
        d = normaliser_date(r["date_facture"])
        if d is not None and d <= d_bl:
            candidats.append((d, r))
    if not candidats:
        return None
    _, r = max(candidats, key=lambda x: x[0])
    return {"date_facture": r["date_facture"], "prix_brut": r["prix_brut"],
            "remise_pct": r["remise_pct"], "prix_net": r["prix_net"]}
