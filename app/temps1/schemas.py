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
    total_ht_affiche: float | None = None      # Net HT à payer (APRÈS déductions de pied)
    # Somme de TOUTES les déductions de pied de facture (escompte, avoir, remise globale,
    # reprise de périmés, opération commerciale…), quel que soit le libellé. Un seul nombre
    # positif. Sert à réconcilier : Σ montant_ht lignes − deductions_pied == total_ht_affiche.
    deductions_pied: float = 0.0


class FactureExtraite(BaseModel):
    type_document: str
    entete: EnteteFacture
    lignes: list[LigneFacture] = []
