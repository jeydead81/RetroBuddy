from app.temps1.schemas import FactureExtraite


def test_parse_facture_minimale():
    data = {
        "type_document": "facture_marchandise",
        "entete": {"labo": "URGO", "numero_facture": "F1", "date_facture": "2026-01-10",
                   "total_ht_affiche": 10.0},
        "lignes": [
            {"code": "3400930000007", "type_code": "CIP13", "code_interne": None,
             "designation": "PRODUIT A", "qte": 2, "qte_gratuite": 0,
             "prix_brut": 6.0, "remise_pct": 10.0, "remises_detail": [],
             "prix_net": 5.0, "montant_ht": 10.0, "tva": 2.1}
        ],
    }
    f = FactureExtraite.model_validate(data)
    assert f.type_document == "facture_marchandise"
    assert f.entete.labo == "URGO"
    assert len(f.lignes) == 1
    assert f.lignes[0].prix_net == 5.0
    assert f.lignes[0].qte_gratuite == 0
