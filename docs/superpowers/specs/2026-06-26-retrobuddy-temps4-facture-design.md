# RetroBuddy — Temps 4 : Édition de la facture de rétrocession — Design

> Quatrième et dernier sous-projet fonctionnel de RetroBuddy. Construit sur les Temps 1-3.
> Cadrage global : `CADRAGE_RETROCESSION.md`.

- **Date** : 2026-06-26
- **Périmètre** : §11 étape 10 du cadrage.
- **Livrable** : éditer la **facture de rétrocession** (regroupée par BL, ventilation TVA,
  totaux) à partir des lignes résolues, avec export **PDF + Excel + CSV** ; la génération est
  **bloquée tant qu'une ligne non résolue (rouge) subsiste**.

---

## 1. Objectif et périmètre

Produire la facture de vente rétrocession destinée à l'acheteur, calquée sur la structure du
document LGO : en-tête (émettrice/destinataire), lignes **regroupées par BL**, et pied avec la
**ventilation de la TVA par taux** et les totaux. La facture intègre le matching automatique
(Temps 2) et les corrections humaines (Temps 3).

**Dans le périmètre :**
- Calcul de la facture (cœur pur testable) : regroupement par BL, `Montant HT = Qté × PA net`,
  ventilation TVA, totaux HT/TVA/TTC, règle de blocage.
- Exports : **PDF** (`reportlab`), **XLSX** (`openpyxl`), **CSV** (stdlib).
- Page web `/facture/{retro_id}` : aperçu + boutons de génération (désactivés si bloqué), et une
  liste `/factures-retro`.

**Hors périmètre (reporté) :**
- **Format graphique exact** « calqué LGO » (logo émetteur, mentions légales) — point ouvert
  §13, à traiter avec la **passe « belle UI » de fin de projet**. Ici : un PDF **propre et
  fonctionnel**, pas le pixel-perfect.
- **Passe 5** (relecture IA des PDF labo) — reste du Temps 3.

---

## 2. Quelles lignes entrent dans la facture ?

Source : `retro_documents` (en-tête) + ses `retro_lignes` (Temps 2-3).

- **Ligne facturable** : `statut_ecart != 'rouge'` (donc `prix_net` renseigné — lignes
  `resolu` et `orange`). Les oranges (candidat par désignation) sont incluses, elles **ne
  bloquent pas** (cadrage §70).
- **Blocage** : la facture est **bloquée** si au moins une `retro_lignes.statut_ecart == 'rouge'`
  (prix manquant). Les boutons de génération sont alors désactivés, et les endpoints de
  téléchargement renvoient `409`.
- `Montant HT (ligne) = round(Qté × PA net, 2)`.

---

## 3. Architecture

| Module | Rôle |
|---|---|
| `app/temps4/facture_builder.py` | Construit l'objet `Facture` (regroupement BL, montants, ventilation TVA, totaux, blocage) — pur, testable. |
| `app/temps4/export_csv.py` | `facture_csv(facture) -> str`. |
| `app/temps4/export_xlsx.py` | `facture_xlsx(facture) -> bytes` (openpyxl → BytesIO). |
| `app/temps4/export_pdf.py` | `facture_pdf(facture) -> bytes` (reportlab → BytesIO). |
| `app/main.py` | Routes `/factures-retro` (liste) + `/facture/{retro_id}` (aperçu) + `/facture/{retro_id}/{pdf|xlsx|csv}` (téléchargement). |
| `app/ui/templates/` | `factures_retro.html`, `facture.html`. |

### 3.1 Structures (`facture_builder.py`)
```python
@dataclass
class LigneFacturee:
    designation: str
    code: str | None
    qte: float
    prix_brut: float | None
    remise_pct: float | None
    prix_net: float
    tva: float | None
    montant_ht: float

@dataclass
class GroupeBL:
    bl_numero: str | None
    bl_date: str | None
    lignes: list[LigneFacturee]

@dataclass
class VentilationTva:
    taux: float
    base_ht: float
    montant_tva: float

@dataclass
class Facture:
    retro_id: int
    emettrice: str | None
    destinataire: str | None
    numero: str | None
    date_vente: str | None
    groupes: list[GroupeBL]
    ventilation: list[VentilationTva]
    total_ht: float
    total_tva: float
    total_ttc: float
    bloquee: bool
    n_rouge: int

def construire_facture(conn, retro_id) -> Facture: ...
```

### 3.2 Calcul
- Lignes facturables triées et regroupées par `(bl_numero, bl_date)`, dans l'ordre des `id`.
- Ventilation : pour chaque taux TVA présent, `base_ht = Σ montant_ht`,
  `montant_tva = round(base_ht × taux/100, 2)`.
- `total_ht = Σ montant_ht` ; `total_tva = Σ montant_tva` (sur la ventilation) ;
  `total_ttc = round(total_ht + total_tva, 2)`.
- `n_rouge = COUNT(statut_ecart='rouge')` ; `bloquee = n_rouge > 0`.

### 3.3 Exports
- **CSV** : en-tête facture, puis lignes (BL, désignation, code, qté, PA brut, remise %, PA net,
  TVA, Montant HT), puis ventilation + totaux. Encodage UTF-8 (BOM pour Excel).
- **XLSX** : même contenu, mise en forme simple (en-tête gras, totaux en bas), via openpyxl.
- **PDF** : en-tête (émettrice/destinataire/numéro/date), un bloc par BL, tableau des lignes,
  pied ventilation TVA + totaux, via reportlab (platypus). Propre, pas pixel-perfect.
- Les trois sérialisent le **même** objet `Facture`. Génération refusée si `facture.bloquee`.

---

## 4. Interface web

- `GET /factures-retro` : liste des `retro_documents` (numéro, émettrice, destinataire, nb
  lignes, nb rouges) avec lien vers `/facture/{id}`.
- `GET /facture/{retro_id}` : aperçu de la facture (groupes par BL, colonnes Désignation/Code/
  Qté/PA brut/Remise %/PA net/TVA/Montant HT, pied ventilation + totaux). Bandeau si **bloquée**
  (« N ligne(s) à compléter avant génération »). Boutons **Générer PDF / Excel / CSV**
  désactivés si bloquée.
- `GET /facture/{retro_id}/pdf` `/xlsx` `/csv` : génèrent et renvoient le fichier en
  téléchargement ; renvoient `409` si la facture est bloquée.
- Nav : ajouter « Factures rétro ».

---

## 5. Modèle de données

Aucune nouvelle table : la facture est **dérivée** de `retro_documents` + `retro_lignes`.
Nouvelles dépendances : `reportlab`, `openpyxl` (ajout à `requirements.txt`).

---

## 6. Stratégie de test

- **facture_builder** : regroupement par BL (2 BL → 2 groupes) ; `montant_ht = qté × prix_net` ;
  ventilation TVA (deux taux → deux entrées, bases correctes) ; totaux HT/TVA/TTC ; exclusion
  des lignes rouges ; `bloquee=True` si une rouge subsiste, `False` sinon ; n_rouge.
- **export_csv** : la chaîne contient l'émettrice, une ligne produit et le total TTC.
- **export_xlsx** : renvoie des bytes non vides commençant par `PK` (zip XLSX).
- **export_pdf** : renvoie des bytes non vides commençant par `%PDF`.
- **web** : `/factures-retro` 200 ; `/facture/{id}` 200 (et affiche le blocage si rouge) ;
  `/facture/{id}/csv` renvoie du CSV quand non bloquée ; `/facture/{id}/pdf` renvoie `409`
  quand bloquée.
- Tout testable **sans appel API** (données en base + génération locale).

---

## 7. Gestion d'erreurs

- `retro_id` inconnu → `404`.
- Facture bloquée + tentative de téléchargement → `409` (message « lignes à compléter »).
- Une facture sans aucune ligne facturable (toutes rouges) est bloquée.

---

## 8. Critères d'acceptation Temps 4

1. `/facture/{retro_id}` affiche les lignes **regroupées par BL** (avec date), colonnes
   Désignation/Code/Qté/PA brut/Remise %/PA net/TVA/Montant HT, et le pied **ventilation TVA +
   Total HT/TVA/TTC**.
2. `Montant HT = Qté × PA net` ; la ventilation TVA additionne correctement par taux ; les
   totaux sont cohérents.
3. Les boutons de génération sont **désactivés** et les téléchargements renvoient `409` tant
   qu'une ligne **rouge** subsiste ; les oranges ne bloquent pas.
4. Les exports **PDF**, **XLSX** et **CSV** se génèrent et contiennent l'en-tête, les lignes et
   les totaux.
5. Le cœur (calcul facture) est couvert par des tests unitaires verts, sans appel API.
