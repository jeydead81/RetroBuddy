import datetime

from app.temps2.normalisation_dates import normaliser_date

# Fenêtre de repli : un prix facturé APRÈS le BL reste acceptable s'il est proche
# (les prix varient peu sur la période). Décision Baptiste : mieux vaut un prix
# légèrement postérieur qu'une ligne en anomalie. ~2 mois.
FENETRE_POSTERIEURE_JOURS = 62


def prix_a_date(conn, code_resolu, bl_date):
    """Prix net du référentiel pour `code_resolu` à la date du BL.

    Priorité : le prix le plus récent avec date_facture <= bl_date. À défaut,
    repli sur le prix POSTÉRIEUR le plus proche dans une fenêtre de
    `FENETRE_POSTERIEURE_JOURS` jours (~2 mois). Au-delà : None (ligne à compléter).
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
    anterieurs, posterieurs = [], []
    limite = d_bl + datetime.timedelta(days=FENETRE_POSTERIEURE_JOURS)
    for r in rows:
        d = normaliser_date(r["date_facture"])
        if d is None:
            continue
        if d <= d_bl:
            anterieurs.append((d, r))
        elif d <= limite:
            posterieurs.append((d, r))
    if anterieurs:
        _, r = max(anterieurs, key=lambda x: x[0])
    elif posterieurs:
        _, r = min(posterieurs, key=lambda x: x[0])   # le plus proche du BL
    else:
        return None
    return {"date_facture": r["date_facture"], "prix_brut": r["prix_brut"],
            "remise_pct": r["remise_pct"], "prix_net": r["prix_net"]}
