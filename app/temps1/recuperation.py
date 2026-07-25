from app.temps1 import selection
from app.temps1.referentiel import enregistrer_referentiel
from app.temps1.schemas import LigneFacture


def factures_recuperables(conn, tol):
    """Factures labo « en revue » POUR CAUSE DE RÉCONCILIATION, dont l'écart s'explique
    par une déduction de pied de facture : Σ montant_ht lignes >= Total HT affiché (net).

    Si Σ < net, des lignes manquent vraiment -> NON récupérable ici (ré-import nécessaire).
    On ne touche pas les « en revue » de classification (autre motif)."""
    return conn.execute(
        "SELECT id, labo, date_facture, total_affiche, total_calcule FROM factures "
        "WHERE statut = 'en_revue' AND motif LIKE '%concili%' "
        "AND total_affiche IS NOT NULL AND total_calcule IS NOT NULL "
        "AND total_calcule >= total_affiche - ?",
        (tol,)).fetchall()


def _net_ligne(l):
    """PA net d'une ligne : celui extrait, sinon reconstitué comme « Récupérer les PA net
    manquants » — brut×(1−remise), à défaut montant÷qté. None si non calculable."""
    if l["prix_net"] is not None:
        return l["prix_net"]
    if l["prix_brut"] and l["remise_pct"] is not None and abs(l["remise_pct"]) < 100:
        return round(l["prix_brut"] * (1 - abs(l["remise_pct"]) / 100), 4)
    if l["montant_ht"] and l["qte"]:
        return round(l["montant_ht"] / l["qte"], 4)
    return None


def _entrees_referentiel(conn, facture_id):
    """Reconstruit les entrées référentiel depuis les lignes déjà stockées (PA net
    reconstitué s'il manque, re-qualification avec la logique de code actuelle). Écrit le
    net calculé + l'inclusion sur la ligne, pour qu'elle sorte du bucket « sans prix »."""
    entrees = []
    for l in conn.execute(
            "SELECT id, code, type_code, code_interne, designation, qte, qte_gratuite, "
            "prix_brut, remise_pct, prix_net, montant_ht, tva FROM lignes_facture "
            "WHERE facture_id = ?", (facture_id,)):
        net = _net_ligne(l)
        lf = LigneFacture(
            code=l["code"], type_code=l["type_code"], code_interne=l["code_interne"],
            designation=l["designation"] or "", qte=l["qte"],
            qte_gratuite=l["qte_gratuite"] or 0, prix_brut=l["prix_brut"],
            remise_pct=l["remise_pct"], prix_net=net,
            montant_ht=l["montant_ht"], tva=l["tva"])
        q = selection.qualifier_ligne(lf)
        conn.execute("UPDATE lignes_facture SET prix_net=?, valide=?, motif_ligne=? WHERE id=?",
                     (net, int(q.inclure), q.note, l["id"]))
        if q.inclure:
            entrees.append((q.code_ref, q.type_code, lf))
    return entrees


def recuperer_en_revue(conn, tol):
    """Repasse les factures récupérables en « ingérée » et verse leurs lignes au référentiel,
    sans ré-import (l'écart = une déduction de pied, les produits sont complets).
    Retourne (n_factures, n_prix)."""
    n_fact = n_ref = 0
    for f in factures_recuperables(conn, tol):
        entrees = _entrees_referentiel(conn, f["id"])
        if entrees:
            enregistrer_referentiel(conn, f["id"], f["date_facture"], f["labo"], entrees)
            n_ref += len(entrees)
        conn.execute("UPDATE factures SET statut = 'ingeree', motif = NULL WHERE id = ?",
                     (f["id"],))
        n_fact += 1
    conn.commit()
    return n_fact, n_ref
