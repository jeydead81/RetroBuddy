from app.codes.checksum import normaliser_code, type_de_code
from app.temps2.calcul_prix import prix_a_date


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


def _alimenter_referentiel(conn, code, date_facture, designation, prix_brut, remise_pct, prix_net):
    """Verse au référentiel le prix saisi/corrigé à la main (source='resolution').

    Écrase la valeur au même (code, date) même si elle venait d'une facture labo :
    une correction manuelle fait autorité. Réversible en supprimant l'entrée au
    référentiel (le prix labo redevient alors la référence)."""
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, type_code, prix_brut, remise_pct, "
        "prix_net, designation, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'resolution') "
        "ON CONFLICT(code, date_facture) DO UPDATE SET prix_brut=excluded.prix_brut, "
        "remise_pct=excluded.remise_pct, prix_net=excluded.prix_net, "
        "designation=excluded.designation, source='resolution'",
        (code, date_facture, type_de_code(code), prix_brut, remise_pct, prix_net, designation))


def _propager(conn, code, exclure_id, retro_id):
    """Applique le prix tout juste saisi/corrigé (via prix_a_date, fenêtre ±6 mois)
    aux autres lignes NON verrouillées (ni validées ni saisies à la main) du même code :
      - MÊME facture (retro_id) : quel que soit leur statut → la correction se propage
        aux lignes sœurs du même produit ;
      - AUTRES factures : uniquement si la ligne est encore ROUGE → on la résout sans
        toucher une ligne déjà rapprochée (le « Re-rapprocher » global s'en charge).
    Retourne le nombre de lignes modifiées."""
    n = 0
    for l in conn.execute(
            "SELECT id, code, bl_date, retro_id, statut_ecart FROM retro_lignes "
            "WHERE valide_utilisateur=0 AND saisie_manuelle=0 AND id != ?", (exclure_id,)):
        if normaliser_code(l["code"]) != code:
            continue
        meme_facture = l["retro_id"] == retro_id
        if not meme_facture and l["statut_ecart"] != "rouge":
            continue
        prix = prix_a_date(conn, code, l["bl_date"])
        if prix is not None and (prix["prix_net"] or 0) > 0:
            conn.execute(
                "UPDATE retro_lignes SET code_resolu=?, prix_brut=?, remise_pct=?, prix_net=?, "
                "statut_ecart='resolu', passe_match=1 WHERE id=?",
                (code, prix["prix_brut"], prix["remise_pct"], prix["prix_net"], l["id"]))
            n += 1
    return n


def enregistrer_ligne(conn, ligne_id, prix_brut=None, remise_pct=None, prix_net=None, ug=0):
    """Sauvegarde une saisie manuelle : recalcule le net (sauf si net fourni), valide la
    ligne, verse le prix au référentiel (source résolution, ±6 mois) et résout d'un coup
    les autres lignes rouges du même produit."""
    ligne = conn.execute(
        "SELECT qte, code, designation, bl_date, retro_id FROM retro_lignes WHERE id=?",
        (ligne_id,)).fetchone()
    qte = ligne["qte"] if ligne else 0
    net = prix_net if prix_net is not None else calcul_net(qte, prix_brut, remise_pct, ug)
    valide = 1 if (net is not None and net > 0) else 0
    statut = "resolu" if valide else "rouge"
    conn.execute(
        "UPDATE retro_lignes SET prix_brut=?, remise_pct=?, prix_net=?, ug=?, "
        "saisie_manuelle=1, valide_utilisateur=?, statut_ecart=? WHERE id=?",
        (prix_brut, remise_pct, net, ug, valide, statut, ligne_id))

    propagees = 0
    if valide and ligne and ligne["code"]:
        code = normaliser_code(ligne["code"])
        if code:
            _alimenter_referentiel(conn, code, ligne["bl_date"], ligne["designation"],
                                   prix_brut, remise_pct, net)
            propagees = _propager(conn, code, ligne_id, ligne["retro_id"])
    conn.commit()
    return {"id": ligne_id, "prix_net": net, "statut_ecart": statut,
            "valide_utilisateur": valide, "propagees": propagees}


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
