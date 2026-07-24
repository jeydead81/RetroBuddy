import datetime

from app.temps2.normalisation_dates import normaliser_date

# Prix labo daté juste APRÈS le BL : accepté si proche (variations minimes). ~2 mois.
FENETRE_POSTERIEURE_JOURS = 62
# Prix SAISI EN RÉSOLUTION : valable ±6 mois autour de sa date (avant ET après).
FENETRE_RESOLUTION_JOURS = 183


def _as_dict(r):
    return {"date_facture": r["date_facture"], "prix_brut": r["prix_brut"],
            "remise_pct": r["remise_pct"], "prix_net": r["prix_net"]}


def _est_resolution(r):
    return r["source"] == "resolution"


def prix_a_date(conn, code_resolu, bl_date):
    """Prix net du référentiel pour `code_resolu` à la date du BL.

    Timeline unifiée labo + correction manuelle : on retient le prix le PLUS RÉCENT
    daté <= BL, quelle que soit la source. Une correction manuelle (source='resolution')
    prime donc sur le labo TANT QU'aucune facture labo plus récente n'a été importée —
    dès qu'une facture plus récente arrive, elle reprend la main automatiquement.
      - Prix labo : valable sans limite en arrière (il persiste jusqu'à être remplacé),
        et en repli postérieur dans `FENETRE_POSTERIEURE_JOURS`.
      - Correction manuelle : retenue seulement dans ±`FENETRE_RESOLUTION_JOURS`
        (avant OU après le BL).
      - À date égale, la correction manuelle l'emporte (on a corrigé CE prix-là).
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

    # 1) Antérieur (date <= BL) le plus récent, toutes sources. Labo sans limite arrière ;
    #    correction retenue seulement dans ±6 mois. À date égale : la correction gagne.
    ant = [(d, r) for d, r in par if d <= d_bl
           and (not _est_resolution(r) or (d_bl - d).days <= FENETRE_RESOLUTION_JOURS)]
    if ant:
        return _as_dict(max(ant, key=lambda x: (x[0], _est_resolution(x[1])))[1])

    # 2) Sinon postérieur le plus proche, dans la fenêtre propre à la source.
    post = [(d, r) for d, r in par if d_bl < d
            and (d - d_bl).days <= (FENETRE_RESOLUTION_JOURS if _est_resolution(r)
                                    else FENETRE_POSTERIEURE_JOURS)]
    if post:
        return _as_dict(min(post, key=lambda x: ((x[0] - d_bl).days, not _est_resolution(x[1])))[1])
    return None
