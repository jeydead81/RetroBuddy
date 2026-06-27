from pydantic import BaseModel


class RetroLigne(BaseModel):
    designation: str
    code: str | None = None
    type_code: str | None = None     # CIP13 | EAN13 | inconnu
    qte: float | None = None
    tva: float | None = None         # Taux TVA (2.1 | 5.5 | 10 | 20), PAS la remise
    bl_numero: str | None = None
    bl_date: str | None = None
    montant_ht: float | None = None  # Montant HT de la ligne — contrôle de complétude only


class RetroEntete(BaseModel):
    pharmacie_emettrice: str | None = None
    pharmacie_destinataire: str | None = None
    date_vente: str | None = None
    numero: str | None = None
    total_ht_affiche: float | None = None   # Total HT du récap — contrôle de complétude


class RetroExtrait(BaseModel):
    type_document: str
    entete: RetroEntete
    lignes: list[RetroLigne] = []
