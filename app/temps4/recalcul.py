from app.temps2.calcul_prix import prix_a_date


def recalculer_prix_facture(conn, retro_id):
    """Re-tire les prix du référentiel pour les lignes d'une rétrocession.

    Sert à propager une correction du référentiel à une facture déjà construite.
    Ne touche **jamais** une ligne saisie à la main (`saisie_manuelle = 1`) ni une
    ligne sans code résolu. Pour chaque ligne éligible, on relit le « dernier prix
    net <= date du BL » (`prix_a_date`) et on met à jour brut/remise/net si un prix
    est trouvé (sinon on laisse la ligne intacte, jamais on ne casse un montant).

    Retourne {"maj": n_lignes_mises_a_jour, "eligibles": n_lignes_examinees}.
    """
    lignes = conn.execute(
        "SELECT id, code_resolu, bl_date FROM retro_lignes "
        "WHERE retro_id = ? AND saisie_manuelle = 0 AND code_resolu IS NOT NULL",
        (retro_id,)).fetchall()
    maj = 0
    for l in lignes:
        prix = prix_a_date(conn, l["code_resolu"], l["bl_date"])
        if prix is None:
            continue
        conn.execute(
            "UPDATE retro_lignes SET prix_brut=?, remise_pct=?, prix_net=? WHERE id=?",
            (prix["prix_brut"], prix["remise_pct"], prix["prix_net"], l["id"]))
        maj += 1
    conn.commit()
    return {"maj": maj, "eligibles": len(lignes)}
