"""Surveillance labo/produit : liste de termes à flaguer en bleu (UG possibles)."""


def termes_surveilles(conn):
    return [r["terme"].strip().lower() for r in conn.execute("SELECT terme FROM surveillance")
            if (r["terme"] or "").strip()]


def est_surveille(designation, code, termes):
    """Vrai si la désignation ou le code contient un terme surveillé (labo/produit à flag)."""
    cible = f"{designation or ''} {code or ''}".lower()
    return any(t in cible for t in termes)
