from app.temps2.schemas import RetroExtrait


def test_parse_retro_minimal():
    data = {
        "type_document": "retro_lgo",
        "entete": {"pharmacie_emettrice": "PHARMACIE SERALY",
                   "pharmacie_destinataire": "PHARMACIE DE CENON",
                   "date_vente": "22/09/2025", "numero": "28955/1552496"},
        "lignes": [
            {"designation": "IMODIUMDUO CPR 12", "code": "3400937882248",
             "type_code": "CIP13", "qte": 2, "tva": 10.0,
             "bl_numero": "28476", "bl_date": "01/08/2025"}
        ],
    }
    r = RetroExtrait.model_validate(data)
    assert r.type_document == "retro_lgo"
    assert r.entete.pharmacie_emettrice == "PHARMACIE SERALY"
    assert len(r.lignes) == 1
    assert r.lignes[0].tva == 10.0
    assert r.lignes[0].bl_date == "01/08/2025"
