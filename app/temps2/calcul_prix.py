import datetime

from app.temps2.normalisation_dates import normaliser_date

# Prix labo daté juste APRÈS le BL : accepté si proche (variations minimes). ~2 mois.
FENETRE_POSTERIEURE_JOURS = 62
# Prix SAISI EN RÉSOLUTION : valable ±6 mois autour de sa date (avant ET après).
FENETRE_RESOLUTION_JOURS = 183


def _as_dict(r):
    return {"date_facture": r["date_facture"], "prix_brut": r["prix_brut"],
            "remise_pct": r["remise_pct"], "prix_net": r["prix_net"]}


def prix_a_date(conn, code_resolu, bl_date):
    """Prix net du référentiel pour `code_resolu` à la date du BL.

    Priorité aux prix de VRAIE facture labo :
      - le plus récent avec date_facture <= bl_date ;
      - à défaut, le postérieur le plus proche dans `FENETRE_POSTERIEURE_JOURS`.
    Repli sur un prix SAISI EN RÉSOLUTION (source='resolution') valable
    ±`FENETRE_RESOLUTION_JOURS` jours autour de sa date (le plus proche du BL).
    Retourne un dict {date_facture, prix_brut, remise_pct, prix_net} ou None.
    """
    d_bl = normaliser_date(bl_date)
    if d_bl is None or not code_resolu:
        return None
    rows = conn.execute(
        "SELECT date_facture, prix_brut, remise_pct, prix_net, "
        "COALESCE(source, 'facture') AS source FROM referentiel_prix WHERE code = ?",
        (code_resolu,),
    ).fetchall()
    par = [(normaliser_date(r["date_facture"]), r) for r in rows]
    par = [(d, r) for d, r in par if d is not None]

    # 1) Prix de vraie facture labo — priorité.
    facture = [(d, r) for d, r in par if r["source"] != "resolution"]
    ant = [(d, r) for d, r in facture if d <= d_bl]
    if ant:
        return _as_dict(max(ant, key=lambda x: x[0])[1])
    post = [(d, r) for d, r in facture
            if d_bl < d <= d_bl + datetime.timedelta(days=FENETRE_POSTERIEURE_JOURS)]
    if post:
        return _as_dict(min(post, key=lambda x: x[0])[1])

    # 2) Repli : prix saisi en résolution, valable ±6 mois autour de sa date.
    reso = [(d, r) for d, r in par
            if r["source"] == "resolution" and abs((d - d_bl).days) <= FENETRE_RESOLUTION_JOURS]
    if reso:
        return _as_dict(min(reso, key=lambda x: abs((x[0] - d_bl).days))[1])
    return None
