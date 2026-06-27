from dataclasses import dataclass

from app.temps2 import calcul_prix, matching
from app.temps2.normalisation_designation import charger_abreviations, dosages_concordants


@dataclass
class ResultatRetro:
    retro_id: int
    n_lignes: int
    n_resolu: int
    n_rouge: int
    cout: float = 0.0
    n_orange: int = 0
    reconciliation_ok: bool = True
    motif_reconciliation: str | None = None


def _reconcilier(retro):
    """Contrôle de complétude : Σ(montant HT des lignes) == Total HT affiché ?

    Tolérance = arrondi cumulé (~0,005 €/ligne), très en-dessous d'une ligne réelle
    (plusieurs €) : une ligne oubliée est détectée sans fausse alerte d'arrondi.
    Retourne (ok: bool, total_calcule: float|None, motif: str|None).
    """
    total = retro.entete.total_ht_affiche
    if total is None:
        return False, None, "Total HT introuvable sur la facture"
    if any(l.montant_ht is None for l in retro.lignes):
        return False, None, "montant absent sur au moins une ligne"
    somme = round(sum(l.montant_ht for l in retro.lignes), 2)
    tol = round(0.02 + 0.005 * len(retro.lignes), 2)
    if abs(somme - total) <= tol:
        return True, somme, None
    return False, somme, f"écart de total : {somme} calculé vs {total} affiché"


def traiter_retro(conn, pdf, extractor, config) -> ResultatRetro:
    retro = extractor.extraire(pdf, config["model_defaut"])
    cout = getattr(extractor, "dernier_cout", 0.0)

    # Garde-fou : la somme des lignes doit réconcilier le Total HT affiché. Sinon,
    # un montant est en jeu -> une seule re-extraction en Opus (2e avis).
    ok, total_calc, motif = _reconcilier(retro)
    if not ok:
        retro = extractor.extraire(pdf, config["model_escalade"])
        cout += getattr(extractor, "dernier_cout", 0.0)
        ok, total_calc, motif = _reconcilier(retro)

    seuil_bas = config.get("seuil_match_bas", 0.80)
    seuil_auto = config.get("seuil_match_auto", 0.95)
    abrev = charger_abreviations(conn)

    cur = conn.execute(
        """
        INSERT INTO retro_documents
          (fichier, pharmacie_emettrice, pharmacie_destinataire, date_vente, numero,
           cout_estime, total_ht_affiche, total_ht_calcule, reconciliation_ok,
           motif_reconciliation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (pdf.nom, retro.entete.pharmacie_emettrice, retro.entete.pharmacie_destinataire,
         retro.entete.date_vente, retro.entete.numero, cout,
         retro.entete.total_ht_affiche, total_calc, int(ok), motif),
    )
    retro_id = cur.lastrowid

    n_resolu = n_rouge = n_orange = 0
    for l in retro.lignes:
        code_resolu, passe = matching.resoudre_code(conn, l.code)   # passes 1-2
        score = None
        cand_desig = None
        if code_resolu is None:                                     # passes 3-4
            cand_code, cand_desig, score = matching.resoudre_par_designation(
                conn, l.designation, seuil_bas, abrev)
            if cand_code is not None and dosages_concordants(l.designation, cand_desig):
                code_resolu = cand_code
                passe = 3 if score >= 1.0 else 4

        prix = calcul_prix.prix_a_date(conn, code_resolu, l.bl_date) if code_resolu else None
        valide = 0
        if prix is not None:
            pb, rp, pn = prix["prix_brut"], prix["remise_pct"], prix["prix_net"]
            if passe in (1, 2):
                statut, n_resolu = "resolu", n_resolu + 1
            else:
                statut, n_orange = "orange", n_orange + 1
                if (score is not None and score >= seuil_auto
                        and dosages_concordants(l.designation, cand_desig)):
                    valide = 1
        else:
            statut, n_rouge = "rouge", n_rouge + 1
            pb = rp = pn = None

        conn.execute(
            """
            INSERT INTO retro_lignes
              (retro_id, designation, code, type_code, qte, tva, bl_numero, bl_date,
               code_resolu, prix_brut, remise_pct, prix_net, passe_match, score_match,
               statut_ecart, valide_utilisateur)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (retro_id, l.designation, l.code, l.type_code, l.qte, l.tva, l.bl_numero,
             l.bl_date, code_resolu, pb, rp, pn, passe, score, statut, valide),
        )
    conn.commit()
    return ResultatRetro(retro_id, len(retro.lignes), n_resolu, n_rouge, cout, n_orange,
                         reconciliation_ok=ok, motif_reconciliation=motif)
