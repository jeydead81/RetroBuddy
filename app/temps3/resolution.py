def calcul_net(qte, prix_brut, remise_pct, ug=0):
    """PA net unitaire (cadrage §3.3) : qte*brut*(1-remise/100)/(qte+ug)."""
    qte = qte or 0
    ug = ug or 0
    if prix_brut is None or (qte + ug) == 0:
        return None
    remise = remise_pct or 0
    return round(qte * prix_brut * (1 - remise / 100) / (qte + ug), 4)


def _qte(conn, ligne_id):
    r = conn.execute("SELECT qte FROM retro_lignes WHERE id=?", (ligne_id,)).fetchone()
    return r["qte"] if r else 0


def enregistrer_ligne(conn, ligne_id, prix_brut=None, remise_pct=None, prix_net=None, ug=0):
    """Sauvegarde une saisie manuelle : recalcule le net (sauf si net fourni), valide la ligne."""
    qte = _qte(conn, ligne_id)
    net = prix_net if prix_net is not None else calcul_net(qte, prix_brut, remise_pct, ug)
    valide = 1 if (net is not None and net > 0) else 0
    statut = "resolu" if valide else "rouge"
    conn.execute(
        "UPDATE retro_lignes SET prix_brut=?, remise_pct=?, prix_net=?, ug=?, "
        "saisie_manuelle=1, valide_utilisateur=?, statut_ecart=? WHERE id=?",
        (prix_brut, remise_pct, net, ug, valide, statut, ligne_id))
    conn.commit()
    return {"id": ligne_id, "prix_net": net, "statut_ecart": statut, "valide_utilisateur": valide}


def accepter_orange(conn, ligne_id):
    """Confirme un candidat orange : la ligne devient résolue."""
    conn.execute(
        "UPDATE retro_lignes SET valide_utilisateur=1, statut_ecart='resolu' WHERE id=?",
        (ligne_id,))
    conn.commit()


def refuser_orange(conn, ligne_id):
    """Rejette un candidat orange : la ligne repasse rouge (à compléter à la main)."""
    conn.execute(
        "UPDATE retro_lignes SET statut_ecart='rouge', valide_utilisateur=0, code_resolu=NULL, "
        "prix_brut=NULL, remise_pct=NULL, prix_net=NULL, passe_match=NULL, score_match=NULL "
        "WHERE id=?",
        (ligne_id,))
    conn.commit()
