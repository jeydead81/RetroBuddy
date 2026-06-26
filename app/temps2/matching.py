from app.codes.correspondance import resoudre_via_correspondance


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
