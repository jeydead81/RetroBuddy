def resoudre_via_correspondance(conn, code):
    """Renvoie un code équivalent (pont CIP<->EAN) via correspondance_codes, ou None."""
    if not code:
        return None
    row = conn.execute(
        "SELECT code_b AS autre FROM correspondance_codes WHERE code_a = ? "
        "UNION "
        "SELECT code_a AS autre FROM correspondance_codes WHERE code_b = ?",
        (code, code),
    ).fetchone()
    return row["autre"] if row else None
