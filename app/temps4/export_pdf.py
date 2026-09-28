import io

from app.format_util import fmt_qte
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, Frame, NextPageTemplate, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

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


_MARGE_G = _MARGE_D = 12 * mm
_MARGE_H = 9 * mm            # page 1 : l'en-tête complet est dans le flux
_MARGE_H_SUITE = 16 * mm     # pages suivantes : place pour l'en-tête compact
_MARGE_B = 12 * mm           # place pour « Page X / Y »


class _CanvasNumerote(rl_canvas.Canvas):
    """Écrit « Page X / Y » en bas de chaque page (Y n'est connu qu'à la fin :
    on mémorise les pages puis on les écrit toutes au save)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for etat in self._pages:
            self.__dict__.update(etat)
            self.setFont("Helvetica", 7)
            self.setFillColor(colors.grey)
            self.drawRightString(A4[0] - _MARGE_D, 6 * mm,
                                 f"Page {self._pageNumber} / {total}")
            super().showPage()
        super().save()


def _nom_fournisseur(facture):
    """Nom court de l'émettrice : 1re ligne des mentions légales, sinon le nom lu."""
    mentions = (getattr(facture, "mentions_emettrice", None) or "").strip()
    return mentions.splitlines()[0].strip() if mentions else (facture.emettrice or "")


def _entete_suite(facture):
    """En-tête compact des pages 2+ : fournisseur, client (+ adresse), n° et date."""
    fournisseur = _nom_fournisseur(facture)
    adresse = ", ".join(l.strip() for l in
                        (getattr(facture, "destinataire_adresse", None) or "").splitlines()
                        if l.strip())

    def dessiner(c, doc):
        c.saveState()
        haut = A4[1] - 8 * mm
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(_MARGE_G, haut, fournisseur)
        c.drawRightString(A4[0] - _MARGE_D, haut, f"Client : {facture.destinataire or ''}")
        c.setFont("Helvetica", 7)
        gauche = f"Facture de rétrocession {facture.numero or ''} du {facture.date_vente or ''}"
        c.drawString(_MARGE_G, haut - 3.4 * mm, gauche)
        if adresse:
            # Adresse sur une ligne, à droite ; police réduite si elle déborderait.
            dispo = A4[0] - _MARGE_G - _MARGE_D - c.stringWidth(gauche, "Helvetica", 7) - 8 * mm
            taille = 7
            while taille > 5 and c.stringWidth(adresse, "Helvetica", taille) > dispo:
                taille -= 0.25
            c.setFont("Helvetica", taille)
            c.drawRightString(A4[0] - _MARGE_D, haut - 3.4 * mm, adresse)
        c.setStrokeColor(colors.grey)
        c.setLineWidth(0.4)
        c.line(_MARGE_G, haut - 5.2 * mm, A4[0] - _MARGE_D, haut - 5.2 * mm)
        c.restoreState()
    return dessiner


def _cadre(id_, marge_haut):
    return Frame(_MARGE_G, _MARGE_B, A4[0] - _MARGE_G - _MARGE_D,
                 A4[1] - marge_haut - _MARGE_B, id=id_,
                 leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)


def facture_pdf(facture):
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=_MARGE_G, rightMargin=_MARGE_D,
                          topMargin=_MARGE_H, bottomMargin=_MARGE_B)
    doc.addPageTemplates([
        PageTemplate("premiere", [_cadre("p1", _MARGE_H)]),
        PageTemplate("suite", [_cadre("pN", _MARGE_H_SUITE)], onPage=_entete_suite(facture)),
    ])
    el = [NextPageTemplate("suite")]

    # En-tête page 1 : émettrice à gauche, titre + client + date en haut à droite.
    larg = A4[0] - _MARGE_G - _MARGE_D
    mentions = getattr(facture, "mentions_emettrice", None)
    gauche = (Paragraph(mentions.replace("\n", "<br/>"), _ST_MENTIONS) if mentions
              else Paragraph(f"Émettrice : <b>{facture.emettrice or ''}</b>", _ST_INFO))
    adresse = getattr(facture, "destinataire_adresse", None)
    dest = f"Facturé à : <b>{facture.destinataire or ''}</b>"
    if adresse:
        dest += "<br/>" + adresse.replace("\n", "<br/>")
    dest += f"<br/>Date : {facture.date_vente or ''}"
    droite = [Paragraph(f"Facture de rétrocession {facture.numero or ''}", _ST_TITRE),
              Paragraph(dest, _ST_INFO)]
    entete = Table([[gauche, droite]], colWidths=[larg * 0.5, larg * 0.5])
    entete.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 6 * mm),
    ]))
    el.append(entete)
    exclues = getattr(facture, "n_rouge", 0) + getattr(facture, "n_a_verifier", 0)
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
        # Total TTC : gros + encadré, sur fond BLANC (lisible en impression noir & blanc).
        ("FONTSIZE", (0, i_ttc), (-1, i_ttc), 12),
        ("BOX", (0, i_ttc), (-1, i_ttc), 1, colors.black),
        ("TOPPADDING", (0, i_ttc), (-1, i_ttc), 4),
        ("BOTTOMPADDING", (0, i_ttc), (-1, i_ttc), 4),
    ]))
    el.append(tv)

    pied = getattr(facture, "pied_facture", None)
    if pied:
        el.append(Spacer(1, 3 * mm))
        el.append(Paragraph(pied.replace("\n", "<br/>"), _ST_MENTIONS))

    doc.build(el, canvasmaker=_CanvasNumerote)
    return buf.getvalue()
