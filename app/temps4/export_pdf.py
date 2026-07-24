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
    exclues = getattr(facture, "n_rouge", 0) + getattr(facture, "n_incoherent", 0)
    if exclues:
        el.append(Paragraph(
            f"<b>FACTURE PARTIELLE</b> — {exclues} ligne(s) exclue(s) du total "
            "(non rapprochée(s) ou prix incohérent).", _ST_INFO))
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

    # Ventilation TVA + totaux dans le même tableau ; Total TTC mis en évidence
    # (gros, fond vert) pour qu'on repère le montant à régler d'un coup d'œil.
    vent = [["Taux TVA", "Base HT", "Montant TVA"]]
    for v in facture.ventilation:
        vent.append([_num(v.taux), _num(v.base_ht, 2), _num(v.montant_tva, 2)])
    i_ht = len(vent);  vent.append(["Total HT", f"{_num(facture.total_ht, 2)} €", ""])
    i_tva = len(vent); vent.append(["Total TVA", f"{_num(facture.total_tva, 2)} €", ""])
    i_ttc = len(vent); vent.append(["Total TTC à régler", f"{_num(facture.total_ttc, 2)} €", ""])
    tv = Table(vent, colWidths=[48 * mm, 22 * mm, 22 * mm], hAlign="LEFT")
    tv.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("ALIGN", (1, 1), (2, i_ht - 1), "RIGHT"),          # valeurs de ventilation à droite
        # Lignes de totaux : label à gauche, valeur alignée à droite sur cols fusionnées.
        ("SPAN", (1, i_ht), (2, i_ht)),
        ("SPAN", (1, i_tva), (2, i_tva)),
        ("SPAN", (1, i_ttc), (2, i_ttc)),
        ("FONTNAME", (0, i_ht), (-1, i_ttc), "Helvetica-Bold"),
        ("ALIGN", (1, i_ht), (-1, i_ttc), "RIGHT"),
        ("LINEABOVE", (0, i_ht), (-1, i_ht), 1.2, colors.HexColor("#15803D")),
        ("FONTSIZE", (0, i_ht), (-1, i_tva), 9),
        # Total TTC : gros, fond vert clair, texte vert foncé.
        ("FONTSIZE", (0, i_ttc), (-1, i_ttc), 12),
        ("BACKGROUND", (0, i_ttc), (-1, i_ttc), colors.HexColor("#DCFCE7")),
        ("TEXTCOLOR", (0, i_ttc), (-1, i_ttc), colors.HexColor("#14532D")),
        ("TOPPADDING", (0, i_ttc), (-1, i_ttc), 4),
        ("BOTTOMPADDING", (0, i_ttc), (-1, i_ttc), 4),
    ]))
    el.append(tv)

    doc.build(el)
    return buf.getvalue()
