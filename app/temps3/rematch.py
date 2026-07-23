from app.temps2 import calcul_prix, matching
from app.temps2.normalisation_designation import charger_abreviations, dosages_concordants


def rematcher(conn, config, progression=None):
    """Rejoue passes 1-4 + calcul prix sur les lignes ni validées ni saisies.

    `progression(fait, total)` est appelé régulièrement (barre de progression).
    Retourne les compteurs {resolu, orange, rouge} des lignes re-traitées.
    """
    seuil_bas = config.get("seuil_match_bas", 0.80)
    seuil_auto = config.get("seuil_match_auto", 0.95)
    abrev = charger_abreviations(conn)
    compteurs = {"resolu": 0, "orange": 0, "rouge": 0}

    lignes = conn.execute(
        "SELECT id, code, designation, bl_date FROM retro_lignes "
        "WHERE valide_utilisateur = 0 AND saisie_manuelle = 0").fetchall()
    total = len(lignes)

    for i, l in enumerate(lignes):
        if progression is not None and i % 25 == 0:
            progression(i, total)
        code_resolu, passe = matching.resoudre_code(conn, l["code"])
        score, cand_desig = None, None
        if code_resolu is None:
            cand_code, cand_desig, score = matching.resoudre_par_designation(
                conn, l["designation"], seuil_bas, abrev)
            if cand_code is not None and dosages_concordants(l["designation"], cand_desig):
                code_resolu = cand_code
                passe = 3 if score >= 1.0 else 4

        prix = calcul_prix.prix_a_date(conn, code_resolu, l["bl_date"]) if code_resolu else None
        valide = 0
        if prix is not None:
            pb, rp, pn = prix["prix_brut"], prix["remise_pct"], prix["prix_net"]
            if passe in (1, 2):
                statut = "resolu"
            else:
                statut = "orange"
                if (score is not None and score >= seuil_auto
                        and dosages_concordants(l["designation"], cand_desig)):
                    valide = 1
        else:
            statut, pb, rp, pn = "rouge", None, None, None

        compteurs[statut] += 1
        conn.execute(
            "UPDATE retro_lignes SET code_resolu=?, prix_brut=?, remise_pct=?, prix_net=?, "
            "passe_match=?, score_match=?, statut_ecart=?, valide_utilisateur=? WHERE id=?",
            (code_resolu, pb, rp, pn, passe, score, statut, valide, l["id"]))
    conn.commit()
    if progression is not None:
        progression(total, total)
    return compteurs
