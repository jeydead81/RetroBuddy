import csv
import io


def facture_csv(facture):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Facture de rétrocession", facture.numero or ""])
    w.writerow(["Émettrice", facture.emettrice or ""])
    w.writerow(["Destinataire", facture.destinataire or ""])
    w.writerow(["Date", facture.date_vente or ""])
    if getattr(facture, "n_rouge", 0):
        w.writerow(["FACTURE PARTIELLE",
                    f"{facture.n_rouge} ligne(s) non rapprochée(s) exclue(s) du total"])
    w.writerow([])
    w.writerow(["BL", "Date BL", "Désignation", "Code", "Qté", "PA brut",
                "Remise %", "PA net", "TVA", "Montant HT"])
    for g in facture.groupes:
        for l in g.lignes:
            w.writerow([g.bl_numero or "", g.bl_date or "", l.designation, l.code or "",
                        l.qte, "" if l.prix_brut is None else l.prix_brut,
                        "" if l.remise_pct is None else l.remise_pct, l.prix_net,
                        "" if l.tva is None else l.tva, l.montant_ht])
    w.writerow([])
    w.writerow(["Ventilation TVA", "Taux", "Base HT", "Montant TVA"])
    for v in facture.ventilation:
        w.writerow(["", v.taux, v.base_ht, v.montant_tva])
    w.writerow([])
    w.writerow(["Total HT", facture.total_ht])
    w.writerow(["Total TVA", facture.total_tva])
    w.writerow(["Total TTC", facture.total_ttc])
    return "﻿" + buf.getvalue()
