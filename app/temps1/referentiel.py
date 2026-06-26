def enregistrer_referentiel(conn, facture_id, date_facture, labo, entrees):
    """Upsert au référentiel historisé (clé : code, date_facture).

    entrees : itérable de tuples (code_ref, type_code, ligne), où `ligne` porte
    prix_brut / remise_pct / prix_net / designation. `code_ref` est soit un
    CIP13/EAN13 valide, soit un code interne (lignes « sans CIP », Option A).
    """
    for code_ref, type_code, l in entrees:
        conn.execute(
            """
            INSERT INTO referentiel_prix
              (code, date_facture, type_code, labo,
               prix_brut, remise_pct, prix_net, designation, facture_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, date_facture) DO UPDATE SET
              type_code=excluded.type_code,
              labo=excluded.labo,
              prix_brut=excluded.prix_brut,
              remise_pct=excluded.remise_pct,
              prix_net=excluded.prix_net,
              designation=excluded.designation,
              facture_id=excluded.facture_id
            """,
            (code_ref, date_facture, type_code, labo,
             l.prix_brut, l.remise_pct, l.prix_net, l.designation, facture_id),
        )
    conn.commit()
