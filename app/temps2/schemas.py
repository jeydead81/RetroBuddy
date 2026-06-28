from pydantic import BaseModel


class RetroLigne(BaseModel):
    designation: str
    code: str | None = None
    type_code: str | None = None     # CIP13 | EAN13 | inconnu
    qte: float | None = None
    tva: float | None = None         # Taux TVA (2.1 | 5.5 | 10 | 20), PAS la remise
    bl_numero: str | None = None
    bl_date: str | None = None
    montant_ht: float | None = None    # Montant HT de la ligne — contrôles de cohérence
    prix_net_lgo: float | None = None  # Prix unitaire Net imprimé — contrôle qté×prix (N3)


class VentilationTvaLgo(BaseModel):
    taux: float                       # 2.1 | 5.5 | 10 | 20
    montant_ht: float                 # Montant HT de ce taux (récap LGO)


class RetroEntete(BaseModel):
    pharmacie_emettrice: str | None = None
    pharmacie_destinataire: str | None = None
    date_vente: str | None = None
    numero: str | None = None
    total_ht_affiche: float | None = None        # Total HT du récap — contrôle (N1)
    ventilation: list[VentilationTvaLgo] = []    # Montant HT par taux — contrôle (N2)


class RetroExtrait(BaseModel):
    type_document: str
    entete: RetroEntete
    lignes: list[RetroLigne] = []
