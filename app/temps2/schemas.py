from pydantic import BaseModel


class RetroLigne(BaseModel):
    designation: str
    code: str | None = None
    type_code: str | None = None     # CIP13 | EAN13 | inconnu
    qte: float | None = None
    tva: float | None = None         # Taux TVA (2.1 | 5.5 | 10 | 20), PAS la remise
    bl_numero: str | None = None
    bl_date: str | None = None


class RetroEntete(BaseModel):
    pharmacie_emettrice: str | None = None
    pharmacie_destinataire: str | None = None
    date_vente: str | None = None
    numero: str | None = None


class RetroExtrait(BaseModel):
    type_document: str
    entete: RetroEntete
    lignes: list[RetroLigne] = []
