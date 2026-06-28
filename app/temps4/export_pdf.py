import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def facture_pdf(facture):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    el = []

    el.append(Paragraph(f"Facture de rétrocession {facture.numero or ''}", styles["Title"]))
    el.append(Paragraph(f"Émettrice : {facture.emettrice or ''}", styles["Normal"]))
    el.append(Paragraph(f"Destinataire : {facture.destinataire or ''}", styles["Normal"]))
    el.append(Paragraph(f"Date : {facture.date_vente or ''}", styles["Normal"]))
    if getattr(facture, "n_rouge", 0):
        el.append(Paragraph(
            f"<b>FACTURE PARTIELLE</b> — {facture.n_rouge} ligne(s) non rapprochée(s) "
            "exclue(s) du total.", styles["Normal"]))
    el.append(Spacer(1, 6 * mm))

    entete = ["Désignation", "Code", "Qté", "PA brut", "Rem.%", "PA net", "TVA", "Montant HT"]
    for g in facture.groupes:
        el.append(Paragraph(
            f"Bon livraison {g.bl_numero or ''} du {g.bl_date or ''}", styles["Heading4"]))
        data = [entete]
        for l in g.lignes:
            data.append([l.designation, l.code or "", l.qte, l.prix_brut, l.remise_pct,
                         l.prix_net, l.tva, l.montant_ht])
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ]))
        el.append(t)
        el.append(Spacer(1, 3 * mm))

    el.append(Spacer(1, 4 * mm))
    vent = [["Taux TVA", "Base HT", "Montant TVA"]]
    for v in facture.ventilation:
        vent.append([v.taux, v.base_ht, v.montant_tva])
    tv = Table(vent)
    tv.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    el.append(tv)
    el.append(Spacer(1, 3 * mm))

    el.append(Paragraph(f"Total HT : {facture.total_ht}", styles["Normal"]))
    el.append(Paragraph(f"Total TVA : {facture.total_tva}", styles["Normal"]))
    el.append(Paragraph(f"<b>Total TTC : {facture.total_ttc}</b>", styles["Normal"]))

    doc.build(el)
    return buf.getvalue()
