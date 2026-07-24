from dataclasses import dataclass, field


@dataclass
class LigneFacturee:
    designation: str
    code: str | None
    qte: float
    prix_brut: float | None
    remise_pct: float | None
    prix_net: float
    tva: float | None
    montant_ht: float
    id: int | None = None     # id de la retro_ligne (édition inline sur la facture)
    ug: float = 0
    incoherente: bool = False        # PA net incohérent avec brut/remise -> à vérifier
    net_attendu: float | None = None  # net cohérent proposé (brut×(1-remise), UG inclus)
    bl_numero: str | None = None
    bl_date: str | None = None


@dataclass
class GroupeBL:
    bl_numero: str | None
    bl_date: str | None
    lignes: list


@dataclass
class VentilationTva:
    taux: float
    base_ht: float
    montant_tva: float


@dataclass
class Facture:
    retro_id: int
    emettrice: str | None
    destinataire: str | None
    numero: str | None
    date_vente: str | None
    groupes: list
    ventilation: list
    total_ht: float
    total_tva: float
    total_ttc: float
    bloquee: bool
    n_rouge: int
    reconciliation_ok: bool = True
    total_ht_affiche: float | None = None
    total_ht_calcule: float | None = None
    motif_reconciliation: str | None = None
    mentions_emettrice: str | None = None   # en-tête légal de la pharmacie émettrice
    n_incoherent: int = 0                    # lignes au prix incohérent (exclues du total)
    lignes_a_verifier: list = field(default_factory=list)


def _remise_effective(prix_brut, prix_net):
    """Remise % déduite du brut et du net (cascade / multi-remises non affichées).

    Retourne None si non calculable (brut nul/absent ou net absent)."""
    if prix_brut and prix_net is not None and prix_brut > 0:
        return round((1 - prix_net / prix_brut) * 100, 2)
    return None


def _net_incoherent(qte, prix_brut, remise_pct, prix_net, ug):
    """Détecte un PA net incohérent avec brut/remise et retourne le net COHÉRENT attendu
    (sinon None). On ne signale QUE l'incohérence non ambiguë : net franchement AU-DESSUS
    du prix remisé (impossible : une remise/cascade ne fait que baisser le net) ou remise
    hors [0;100]. Un net plus BAS (cascade légitime) n'est jamais signalé. Ne se prononce
    pas si la remise est absente (cascade) ou si les données sont incomplètes."""
    if prix_brut is None or remise_pct is None or prix_net is None:
        return None
    q = qte or 0
    u = ug or 0
    if (q + u) <= 0 or prix_brut <= 0:
        return None
    attendu = round(q * prix_brut * (1 - remise_pct / 100) / (q + u), 4)
    tol = max(0.01, 0.01 * abs(attendu))
    if remise_pct < -0.01 or remise_pct > 100.01 or prix_net > attendu + tol:
        return attendu
    return None


def construire_facture(conn, retro_id):
    doc = conn.execute(
        "SELECT pharmacie_emettrice, pharmacie_destinataire, numero, date_vente, "
        "reconciliation_ok, total_ht_affiche, total_ht_calcule, motif_reconciliation "
        "FROM retro_documents WHERE id = ?", (retro_id,)).fetchone()
    if doc is None:
        return None
    reco_ok = doc["reconciliation_ok"] != 0   # None (anciennes lignes) -> considéré OK
    emet = (doc["pharmacie_emettrice"] or "").strip()
    ent = conn.execute("SELECT mentions FROM entetes_facture WHERE emettrice = ?",
                       (emet,)).fetchone()
    mentions = ent["mentions"] if ent else None
    if mentions is None and emet:                         # repli : casse / espaces
        cible = " ".join(emet.upper().split())
        for r in conn.execute("SELECT emettrice, mentions FROM entetes_facture"):
            if " ".join((r["emettrice"] or "").upper().split()) == cible:
                mentions = r["mentions"]
                break

    lignes = conn.execute(
        "SELECT id, designation, code, qte, prix_brut, remise_pct, prix_net, tva, ug, "
        "bl_numero, bl_date, statut_ecart FROM retro_lignes WHERE retro_id = ? ORDER BY id",
        (retro_id,)).fetchall()
    n_rouge = sum(1 for l in lignes if l["statut_ecart"] == "rouge")

    groupes = []
    courant = None
    total_ht = 0.0
    bases = {}
    a_verifier = []
    for l in lignes:
        if l["statut_ecart"] == "rouge":
            continue
        qte = l["qte"] or 0
        prix_net = l["prix_net"] or 0
        montant = round(qte * prix_net, 2)
        # Remise en cascade / multi-lignes : remise_pct non renseignée mais brut+net
        # présents -> on affiche la remise effective calculée (1 - net/brut)*100.
        remise = l["remise_pct"]
        if remise is None:
            remise = _remise_effective(l["prix_brut"], l["prix_net"])
        # Garde-fou : PA net incohérent -> ligne signalée, JAMAIS facturée tant que non
        # corrigée (exclue du total, comme une ligne non rapprochée).
        net_attendu = _net_incoherent(qte, l["prix_brut"], l["remise_pct"], prix_net, l["ug"] or 0)
        if net_attendu is not None:
            a_verifier.append(LigneFacturee(
                l["designation"], l["code"], qte, l["prix_brut"], remise, prix_net,
                l["tva"], montant, id=l["id"], ug=l["ug"] or 0,
                incoherente=True, net_attendu=net_attendu,
                bl_numero=l["bl_numero"], bl_date=l["bl_date"]))
            continue
        total_ht = round(total_ht + montant, 2)
        taux = l["tva"] if l["tva"] is not None else 0.0
        bases[taux] = round(bases.get(taux, 0.0) + montant, 2)
        lf = LigneFacturee(l["designation"], l["code"], qte, l["prix_brut"],
                           remise, prix_net, l["tva"], montant,
                           id=l["id"], ug=l["ug"] or 0)
        cle = (l["bl_numero"], l["bl_date"])
        if courant is None or (courant.bl_numero, courant.bl_date) != cle:
            courant = GroupeBL(l["bl_numero"], l["bl_date"], [])
            groupes.append(courant)
        courant.lignes.append(lf)
    n_incoherent = len(a_verifier)

    ventilation = []
    total_tva = 0.0
    for taux in sorted(bases):
        tva = round(bases[taux] * taux / 100, 2)
        total_tva = round(total_tva + tva, 2)
        ventilation.append(VentilationTva(taux, bases[taux], tva))
    total_ttc = round(total_ht + total_tva, 2)

    return Facture(retro_id, doc["pharmacie_emettrice"], doc["pharmacie_destinataire"],
                   doc["numero"], doc["date_vente"], groupes, ventilation,
                   total_ht, total_tva, total_ttc,
                   bloquee=(n_rouge > 0 or n_incoherent > 0 or not reco_ok), n_rouge=n_rouge,
                   reconciliation_ok=reco_ok,
                   total_ht_affiche=doc["total_ht_affiche"],
                   total_ht_calcule=doc["total_ht_calcule"],
                   motif_reconciliation=doc["motif_reconciliation"],
                   mentions_emettrice=mentions,
                   n_incoherent=n_incoherent, lignes_a_verifier=a_verifier)
