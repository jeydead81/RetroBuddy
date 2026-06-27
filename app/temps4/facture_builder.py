from dataclasses import dataclass


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


def construire_facture(conn, retro_id):
    doc = conn.execute(
        "SELECT pharmacie_emettrice, pharmacie_destinataire, numero, date_vente, "
        "reconciliation_ok, total_ht_affiche, total_ht_calcule, motif_reconciliation "
        "FROM retro_documents WHERE id = ?", (retro_id,)).fetchone()
    if doc is None:
        return None
    reco_ok = doc["reconciliation_ok"] != 0   # None (anciennes lignes) -> considéré OK

    lignes = conn.execute(
        "SELECT designation, code, qte, prix_brut, remise_pct, prix_net, tva, "
        "bl_numero, bl_date, statut_ecart FROM retro_lignes WHERE retro_id = ? ORDER BY id",
        (retro_id,)).fetchall()
    n_rouge = sum(1 for l in lignes if l["statut_ecart"] == "rouge")

    groupes = []
    courant = None
    total_ht = 0.0
    bases = {}
    for l in lignes:
        if l["statut_ecart"] == "rouge":
            continue
        qte = l["qte"] or 0
        prix_net = l["prix_net"] or 0
        montant = round(qte * prix_net, 2)
        total_ht = round(total_ht + montant, 2)
        taux = l["tva"] if l["tva"] is not None else 0.0
        bases[taux] = round(bases.get(taux, 0.0) + montant, 2)
        lf = LigneFacturee(l["designation"], l["code"], qte, l["prix_brut"],
                           l["remise_pct"], prix_net, l["tva"], montant)
        cle = (l["bl_numero"], l["bl_date"])
        if courant is None or (courant.bl_numero, courant.bl_date) != cle:
            courant = GroupeBL(l["bl_numero"], l["bl_date"], [])
            groupes.append(courant)
        courant.lignes.append(lf)

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
                   bloquee=(n_rouge > 0 or not reco_ok), n_rouge=n_rouge,
                   reconciliation_ok=reco_ok,
                   total_ht_affiche=doc["total_ht_affiche"],
                   total_ht_calcule=doc["total_ht_calcule"],
                   motif_reconciliation=doc["motif_reconciliation"])
