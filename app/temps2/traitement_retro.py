from dataclasses import dataclass

from app.temps1.pdf_split import decouper_pdf, nombre_pages
from app.temps2 import calcul_prix, matching
from app.temps2.normalisation_designation import charger_abreviations, dosages_concordants
from app.temps2.schemas import RetroEntete, RetroExtrait


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


# En-dessous de ce seuil (€), un écart est du bruit d'arrondi, non significatif.
TOLERANCE_MIN_EUR = 1.0

# Une facture de ~180 lignes sature le plafond de tokens de sortie (extraction en un
# appel tronquée). Au-delà de SEUIL_PAGES_SIMPLE pages on découpe d'emblée ; sinon on
# tente un appel unique et on ne découpe qu'en cas de troncature.
SEUIL_PAGES_SIMPLE = 12
PAGES_PAR_LOT = 6


def _est_troncature(e) -> bool:
    """Vrai si l'exception traduit une réponse tronquée par le plafond de tokens
    (JSON incomplet côté SDK, ou notre ExtractionError « tronquée »)."""
    s = str(e).lower()
    return any(k in s for k in ("tronqu", "invalid json", "eof while parsing", "json_invalid"))


def _fusionner(morceaux):
    """Fusionne les RetroExtrait des sous-PDF (dans l'ordre des pages). L'en-tête vient
    du 1er morceau ; le Total HT affiché et la ventilation du morceau qui les porte (le
    récap est sur la dernière page). Reporte le BL sur les lignes de continuation : un BL
    peut déborder d'un morceau au suivant, dont la 1re ligne n'a pas revu l'en-tête « Bon
    livraison »."""
    lignes, entete, total, ventilation, type_doc = [], None, None, [], "retrocession"
    for sous in morceaux:
        if entete is None:
            entete = sous.entete
        if sous.entete.total_ht_affiche is not None:
            total = sous.entete.total_ht_affiche
        if sous.entete.ventilation:
            ventilation = sous.entete.ventilation
        if sous.type_document:
            type_doc = sous.type_document
        lignes.extend(sous.lignes)
    bl_num = bl_date = None
    for l in lignes:
        if l.bl_numero:
            bl_num, bl_date = l.bl_numero, l.bl_date
        elif bl_num:
            l.bl_numero, l.bl_date = bl_num, bl_date
    if entete is None:
        entete = RetroEntete()
    entete.total_ht_affiche = total
    entete.ventilation = ventilation
    return RetroExtrait(type_document=type_doc, entete=entete, lignes=lignes)


def _extraire_par_morceaux(extractor, pdf, model):
    morceaux, cout = [], 0.0
    for m in decouper_pdf(pdf, PAGES_PAR_LOT):
        morceaux.append(extractor.extraire(m, model))
        cout += getattr(extractor, "dernier_cout", 0.0)
    extractor.dernier_cout = cout
    return _fusionner(morceaux)


def extraire_retro(extractor, pdf, model):
    """Extraction retro robuste aux factures longues : un seul appel si la facture tient
    sous le plafond de tokens, sinon découpage par paquets de pages puis fusion. Aucune
    ligne perdue en silence : la réconciliation Σ montant_ht == Total HT affiché le vérifie."""
    if nombre_pages(pdf) > SEUIL_PAGES_SIMPLE:
        return _extraire_par_morceaux(extractor, pdf, model)
    try:
        return extractor.extraire(pdf, model)
    except Exception as e:
        if not _est_troncature(e):
            raise
        return _extraire_par_morceaux(extractor, pdf, model)


def _reconcilier(retro, tol_min=TOLERANCE_MIN_EUR):
    """Contrôles de cohérence de l'extraction. Au premier échec -> motif explicite.

    N1 — complétude : Σ(montant HT lignes) == Total HT affiché (aucune ligne oubliée).
    N3 — ligne : qté × prix net == montant (attrape une qté mal lue) ; une ligne dont
                 la qté ou le net manque n'est pas vérifiable, mais son montant est déjà
                 couvert par N1 -> on l'ignore (pas d'échec).
    N2 — TVA : Σ(montant HT par taux) == Montant HT du taux dans la ventilation LGO
              (attrape une TVA mal affectée).
    Tolérance = max(`tol_min`, arrondi cumulé ~0,005 €/ligne) : un écart < `tol_min`
    (1 € par défaut) n'est pas considéré comme significatif.
    Retourne (ok: bool, total_calcule: float|None, motif: str|None).
    """
    lignes = retro.lignes
    total = retro.entete.total_ht_affiche
    if total is None:
        return False, None, "Total HT introuvable sur la facture"
    if any(l.montant_ht is None for l in lignes):
        return False, None, "montant HT absent sur au moins une ligne"
    somme = round(sum(l.montant_ht for l in lignes), 2)

    # N1 — complétude
    if abs(somme - total) > max(tol_min, round(0.02 + 0.005 * len(lignes), 2)):
        return False, somme, f"écart de total : {somme} calculé vs {total} affiché"

    # N3 — cohérence ligne (qté × prix net == montant) ; ligne incomplète -> ignorée
    for l in lignes:
        if l.qte is None or l.prix_net_lgo is None:
            continue
        if abs(round(l.qte * l.prix_net_lgo, 2) - l.montant_ht) > tol_min:
            return False, somme, f"ligne incohérente (qté×prix ≠ montant) : {l.designation}"

    # N2 — cohérence TVA (Σ par taux == ventilation)
    if not retro.entete.ventilation:
        return False, somme, "ventilation TVA absente de la facture"
    par_taux = {}
    for l in lignes:
        if l.tva is None:
            return False, somme, f"taux TVA absent : {l.designation}"
        k = round(l.tva, 2)
        par_taux[k] = round(par_taux.get(k, 0.0) + l.montant_ht, 2)
    taux_ventiles = {round(v.taux, 2) for v in retro.entete.ventilation}
    for k in par_taux:
        if k not in taux_ventiles:
            return False, somme, f"taux TVA {k}% sur des lignes mais absent de la ventilation"
    for v in retro.entete.ventilation:
        k = round(v.taux, 2)
        n_k = sum(1 for l in lignes if round(l.tva, 2) == k)
        if abs(par_taux.get(k, 0.0) - v.montant_ht) > max(tol_min, round(0.02 + 0.005 * n_k, 2)):
            return False, somme, f"écart TVA {v.taux}% : {par_taux.get(k, 0.0)} vs {v.montant_ht} affiché"

    return True, somme, None


def traiter_retro(conn, pdf, extractor, config) -> ResultatRetro:
    retro = extraire_retro(extractor, pdf, config["model_defaut"])
    cout = getattr(extractor, "dernier_cout", 0.0)

    # Garde-fou : la somme des lignes doit réconcilier le Total HT affiché. Sinon,
    # un montant est en jeu -> une seule re-extraction en Opus (2e avis).
    tol = config.get("tolerance_reconciliation_eur", TOLERANCE_MIN_EUR)
    ok, total_calc, motif = _reconcilier(retro, tol)
    if not ok:
        retro = extraire_retro(extractor, pdf, config["model_escalade"])
        cout += getattr(extractor, "dernier_cout", 0.0)
        ok, total_calc, motif = _reconcilier(retro, tol)

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
