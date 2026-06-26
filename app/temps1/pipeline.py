from dataclasses import dataclass

from app.temps1 import classifier, garde_fous, selection
from app.temps1.referentiel import enregistrer_referentiel


@dataclass
class Resultat:
    statut: str               # 'ingeree' | 'ignoree' | 'en_revue'
    motif: str | None
    facture_id: int | None
    total_calcule: float | None
    n_referentiel: int
    cout: float = 0.0         # coût $ d'extraction (Sonnet + éventuelle escalade Opus)


def _qualifier(facture):
    return [(l, selection.qualifier_ligne(l)) for l in facture.lignes]


def _persister(conn, pdf, facture, statut, motif, modele, total_calcule, qualifs, cout):
    cur = conn.execute(
        """
        INSERT INTO factures
          (fichier, labo, numero_facture, date_facture, type_document,
           total_affiche, total_calcule, statut, motif, modele_extraction, cout_estime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (pdf.nom, facture.entete.labo, facture.entete.numero_facture,
         facture.entete.date_facture, facture.type_document,
         facture.entete.total_ht_affiche, total_calcule, statut, motif, modele, cout),
    )
    facture_id = cur.lastrowid
    for l, q in qualifs:
        cok = garde_fous.checksum_ok(l)
        type_code = q.type_code or l.type_code
        conn.execute(
            """
            INSERT INTO lignes_facture
              (facture_id, code, type_code, code_interne, designation, qte, qte_gratuite,
               prix_brut, remise_pct, prix_net, montant_ht, tva, checksum_ok, valide, motif_ligne)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (facture_id, l.code, type_code, l.code_interne, l.designation, l.qte,
             l.qte_gratuite, l.prix_brut, l.remise_pct, l.prix_net, l.montant_ht, l.tva,
             int(cok), int(q.inclure), q.note),
        )
    conn.commit()
    return facture_id


def traiter_facture(conn, pdf, extractor, config) -> Resultat:
    seuil = config["seuil_reconciliation_pct"]
    cout = 0.0

    modele = config["model_defaut"]
    facture = extractor.extraire(pdf, modele)
    cout += getattr(extractor, "dernier_cout", 0.0)
    qualifs = _qualifier(facture)

    dec, motif = classifier.decision(facture)
    if dec == "ignorer":
        fid = _persister(conn, pdf, facture, "ignoree", motif, modele, None, qualifs, cout)
        return Resultat("ignoree", motif, fid, None, 0, cout)

    ok, total = garde_fous.reconcilier_totaux(
        facture.lignes, facture.entete.total_ht_affiche, seuil)

    if not ok:
        # Escalade : une seule re-extraction en Opus
        modele = config["model_escalade"]
        facture = extractor.extraire(pdf, modele)
        cout += getattr(extractor, "dernier_cout", 0.0)
        qualifs = _qualifier(facture)
        dec, motif = classifier.decision(facture)
        if dec == "ignorer":
            fid = _persister(conn, pdf, facture, "ignoree", motif, modele, None, qualifs, cout)
            return Resultat("ignoree", motif, fid, None, 0, cout)
        ok, total = garde_fous.reconcilier_totaux(
            facture.lignes, facture.entete.total_ht_affiche, seuil)
        if not ok:
            m = "totaux non réconciliés (Sonnet + Opus)"
            fid = _persister(conn, pdf, facture, "en_revue", m, modele, total, qualifs, cout)
            return Resultat("en_revue", m, fid, total, 0, cout)

    fid = _persister(conn, pdf, facture, "ingeree", None, modele, total, qualifs, cout)
    entrees = [(q.code_ref, q.type_code, l) for l, q in qualifs if q.inclure]
    enregistrer_referentiel(conn, fid, facture.entete.date_facture,
                            facture.entete.labo, entrees)
    return Resultat("ingeree", None, fid, total, len(entrees), cout)
