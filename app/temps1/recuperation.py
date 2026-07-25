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


def _entrees_referentiel(conn, facture_id):
    """Reconstruit les entrées référentiel depuis les lignes déjà stockées (re-qualifiées
    avec la logique de code actuelle)."""
    entrees = []
    for l in conn.execute(
            "SELECT code, type_code, code_interne, designation, qte, qte_gratuite, "
            "prix_brut, remise_pct, prix_net, montant_ht, tva FROM lignes_facture "
            "WHERE facture_id = ?", (facture_id,)):
        lf = LigneFacture(
            code=l["code"], type_code=l["type_code"], code_interne=l["code_interne"],
            designation=l["designation"] or "", qte=l["qte"],
            qte_gratuite=l["qte_gratuite"] or 0, prix_brut=l["prix_brut"],
            remise_pct=l["remise_pct"], prix_net=l["prix_net"],
            montant_ht=l["montant_ht"], tva=l["tva"])
        q = selection.qualifier_ligne(lf)
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
