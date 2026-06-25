def enregistrer_lignes_referentiel(conn, facture_id, date_facture, lignes):
    """Upsert des lignes retenues dans le référentiel historisé (code, date_facture)."""
    for l in lignes:
        conn.execute(
            """
            INSERT INTO referentiel_prix
              (code, date_facture, prix_brut, remise_pct, prix_net, designation, facture_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, date_facture) DO UPDATE SET
              prix_brut=excluded.prix_brut,
              remise_pct=excluded.remise_pct,
              prix_net=excluded.prix_net,
              designation=excluded.designation,
              facture_id=excluded.facture_id
            """,
            (l.code, date_facture, l.prix_brut, l.remise_pct, l.prix_net,
             l.designation, facture_id),
        )
    conn.commit()
