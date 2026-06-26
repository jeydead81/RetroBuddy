from app.codes.correspondance import resoudre_via_correspondance
from app.temps2.normalisation_designation import normaliser_designation, score_designation


def _code_au_referentiel(conn, code):
    if not code:
        return False
    return conn.execute(
        "SELECT 1 FROM referentiel_prix WHERE code = ? LIMIT 1", (code,)
    ).fetchone() is not None


def resoudre_code(conn, code):
    """Passe 1 (code identique) puis passe 2 (pont CIP<->EAN).

    Retourne (code_resolu, passe) ou (None, None).
    """
    if _code_au_referentiel(conn, code):
        return (code, 1)
    autre = resoudre_via_correspondance(conn, code)
    if autre and _code_au_referentiel(conn, autre):
        return (autre, 2)
    return (None, None)


def resoudre_par_designation(conn, designation, seuil_bas, abreviations=None):
    """Cherche dans le référentiel la meilleure désignation proche (passes 3-4).

    Retourne (code, designation_referentiel, score) si score >= seuil_bas,
    sinon (None, None, 0.0).
    """
    cible = normaliser_designation(designation, abreviations)
    if not cible:
        return (None, None, 0.0)
    meilleur = (None, None, 0.0)
    vu = set()
    for r in conn.execute(
            "SELECT DISTINCT code, designation FROM referentiel_prix WHERE code IS NOT NULL"):
        cle = (r["code"], r["designation"])
        if cle in vu:
            continue
        vu.add(cle)
        s = score_designation(cible, normaliser_designation(r["designation"], abreviations))
        if s > meilleur[2]:
            meilleur = (r["code"], r["designation"], s)
    if meilleur[2] >= seuil_bas:
        return meilleur
    return (None, None, 0.0)
