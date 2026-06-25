from pydantic import BaseModel


class LigneFacture(BaseModel):
    code: str | None = None
    type_code: str | None = None
    code_interne: str | None = None
    designation: str
    qte: float | None = None
    qte_gratuite: float = 0
    prix_brut: float | None = None
    remise_pct: float | None = None
    remises_detail: list[float] = []
    prix_net: float | None = None
    montant_ht: float | None = None
    tva: float | None = None


class EnteteFacture(BaseModel):
    labo: str | None = None
    numero_facture: str | None = None
    date_facture: str | None = None
    total_ht_affiche: float | None = None


class FactureExtraite(BaseModel):
    type_document: str
    entete: EnteteFacture
    lignes: list[LigneFacture] = []
