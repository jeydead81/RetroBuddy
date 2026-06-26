from dataclasses import dataclass

from app.temps2 import calcul_prix, matching


@dataclass
class ResultatRetro:
    retro_id: int
    n_lignes: int
    n_resolu: int
    n_rouge: int
    cout: float = 0.0


def traiter_retro(conn, pdf, extractor, config) -> ResultatRetro:
    retro = extractor.extraire(pdf, config["model_defaut"])
    cout = getattr(extractor, "dernier_cout", 0.0)

    cur = conn.execute(
        """
        INSERT INTO retro_documents
          (fichier, pharmacie_emettrice, pharmacie_destinataire, date_vente, numero, cout_estime)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (pdf.nom, retro.entete.pharmacie_emettrice, retro.entete.pharmacie_destinataire,
         retro.entete.date_vente, retro.entete.numero, cout),
    )
    retro_id = cur.lastrowid

    n_resolu = n_rouge = 0
    for l in retro.lignes:
        code_resolu, passe = matching.resoudre_code(conn, l.code)
        prix = calcul_prix.prix_a_date(conn, code_resolu, l.bl_date) if code_resolu else None
        if prix is not None:
            statut, n_resolu = "resolu", n_resolu + 1
            pb, rp, pn = prix["prix_brut"], prix["remise_pct"], prix["prix_net"]
        else:
            statut, n_rouge = "rouge", n_rouge + 1
            pb = rp = pn = None
        conn.execute(
            """
            INSERT INTO retro_lignes
              (retro_id, designation, code, type_code, qte, tva, bl_numero, bl_date,
               code_resolu, prix_brut, remise_pct, prix_net, passe_match, statut_ecart)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (retro_id, l.designation, l.code, l.type_code, l.qte, l.tva, l.bl_numero,
             l.bl_date, code_resolu, pb, rp, pn, passe, statut),
        )
    conn.commit()
    return ResultatRetro(retro_id, len(retro.lignes), n_resolu, n_rouge, cout)
