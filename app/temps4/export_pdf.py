import io

from app.format_util import fmt_qte
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Mise en page volontairement compacte (demande Baptiste) : marges réduites,
# table unique avec sous-en-têtes par BL, petite police — vise ~2x moins de pages.

_ST_TITRE = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=12, leading=14,
                           spaceAfter=2)
_ST_MENTIONS = ParagraphStyle("mentions", fontName="Helvetica", fontSize=6.5, leading=7.6)
_ST_INFO = ParagraphStyle("info", fontName="Helvetica", fontSize=8, leading=10)
_ST_CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=6.5, leading=7.2)


def _num(v, dec=None):
    if v is None:
        return ""
    if dec is not None:
        return f"{v:.{dec}f}"
    return f"{v:g}"


def facture_pdf(facture):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=9 * mm, bottomMargin=9 * mm,
                            leftMargin=12 * mm, rightMargin=12 * mm)
    el = []

    mentions = getattr(facture, "mentions_emettrice", None)
    if mentions:                                          # en-tête légal de l'émettrice
        el.append(Paragraph(mentions.replace("\n", "<br/>"), _ST_MENTIONS))
        el.append(Spacer(1, 2 * mm))
    el.append(Paragraph(f"Facture de rétrocession {facture.numero or ''}", _ST_TITRE))
    entete_info = ""
    if not mentions:
        entete_info += f"Émettrice : <b>{facture.emettrice or ''}</b> · "
    entete_info += (f"Destinataire : <b>{facture.destinataire or ''}</b>"
                    f" · Date : {facture.date_vente or ''}")
    el.append(Paragraph(entete_info, _ST_INFO))
    if getattr(facture, "n_rouge", 0):
        el.append(Paragraph(
            f"<b>FACTURE PARTIELLE</b> — {facture.n_rouge} ligne(s) non rapprochée(s) "
            "exclue(s) du total.", _ST_INFO))
    el.append(Spacer(1, 2.5 * mm))

    # Table unique : 1 rangée d'en-tête (répétée à chaque page), puis pour chaque BL
    # une rangée-titre fusionnée suivie de ses lignes.
    data = [["Désignation", "Code", "Qté", "PA brut", "Rem.%", "PA net", "TVA", "Montant HT"]]
    styles = [
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDDDDD")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 0.75),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.75),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
    ]
    for g in facture.groupes:
        i = len(data)
        data.append([f"Bon livraison {g.bl_numero or ''} du {g.bl_date or ''}",
                     "", "", "", "", "", "", ""])
        styles += [("SPAN", (0, i), (-1, i)),
                   ("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"),
                   ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F0F0F0")),
                   ("ALIGN", (0, i), (-1, i), "LEFT")]
        for l in g.lignes:
            data.append([Paragraph(l.designation or "", _ST_CELL), l.code or "",
                         fmt_qte(l.qte), _num(l.prix_brut), _num(l.remise_pct),
                         _num(l.prix_net), _num(l.tva), _num(l.montant_ht, 2)])

    t = Table(data, repeatRows=1, colWidths=[
        80 * mm, 23 * mm, 9 * mm, 15 * mm, 11 * mm, 15 * mm, 9 * mm, 17 * mm])
    t.setStyle(TableStyle(styles))
    el.append(t)
    el.append(Spacer(1, 3 * mm))

    vent = [["Taux TVA", "Base HT", "Montant TVA"]]
    for v in facture.ventilation:
        vent.append([_num(v.taux), _num(v.base_ht, 2), _num(v.montant_tva, 2)])
    tv = Table(vent, colWidths=[22 * mm, 24 * mm, 26 * mm], hAlign="LEFT")
    tv.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    el.append(tv)
    el.append(Spacer(1, 2 * mm))

    el.append(Paragraph(
        f"Total HT : {_num(facture.total_ht, 2)} € · Total TVA : {_num(facture.total_tva, 2)} € · "
        f"<b>Total TTC : {_num(facture.total_ttc, 2)} €</b>", _ST_INFO))

    doc.build(el)
    return buf.getvalue()
