# RetroBuddy — Temps 2 : Ingestion LGO + Matching + Calcul prix — Design

> Deuxième sous-projet de RetroBuddy. Construit sur le Temps 1 (référentiel prix).
> Cadrage global : `CADRAGE_RETROCESSION.md`. Spec Temps 1 :
> `docs/superpowers/specs/2026-06-25-retrobuddy-temps1-referentiel-design.md`.

- **Date** : 2026-06-26
- **Périmètre** : §11 étapes 6-7 du cadrage.
- **Livrable** : ingérer une **facture de vente rétrocession du LGO** (PDF), **rapprocher
  chaque ligne du référentiel par code** (passes 1-2), et calculer le prix =
  **dernier prix net ≤ date du BL** de la ligne. Tout ce qui n'est pas rapproché est
  signalé (`rouge` « prix manquant »), jamais inventé.

---

## 1. Objectif et périmètre

Transformer une facture LGO (LGPI) en **lignes de rétrocession chiffrées** prêtes pour la
résolution humaine (Temps 3) puis l'édition de facture (Temps 4). On réutilise le
**référentiel prix** construit au Temps 1 comme source de coût.

**Dans le périmètre :**
- Extraction LGO (prompt B) : en-tête (émettrice, destinataire, date, n°) + lignes
  (désignation, code, qté, TVA, n°/date de BL).
- Matching **passes 1-2** par code (CIP↔CIP, EAN↔EAN, pont CIP↔EAN via table).
- Calcul prix « dernier prix net ≤ date BL ».
- Stockage `retro_documents` / `retro_lignes`.
- Même UX que Temps 1 : ingestion fichier par fichier, **compteur X/N + coût**.

**Hors périmètre (plus tard) :**
- Passes 3-5 (matching par **désignation**, score IA, retour factures) — étape 9.
- Interface de **résolution d'écarts** type Excel, compteurs, couleurs (Temps 3).
- Édition de la facture de rétrocession (Temps 4).
- Gestion des UG en saisie (Temps 3/4).

**Conséquence actée** : les lignes « sans CIP » du référentiel (AbbVie, stockées sous code
interne, cf. Temps 1 Option A) **ne matchent pas** en passes 1-2 (qui comparent des
CIP/EAN). Ces produits ressortent en `rouge` jusqu'au matching par désignation (étape 9).

---

## 2. Structure réelle de la facture LGO (observée)

Sur l'échantillon `data/samples/factures_lgo/retroCenon310825Offic.pdf` (9 pages) :

- **En-tête (répété par page)** : bloc société en haut = **émettrice/vendeur** (PHARMACIE
  SERALY) ; bloc après la légende = **destinataire/acheteur** (PHARMACIE DE CENON).
  « VENTE RETROCESSION éditée le 22/09/2025 », « N°28955/1552496 »,
  « Vente réalisée le 22/09/2025 ».
- **Regroupement par BL** : en-têtes `Bon livraison <numéro> du <jj/mm/aaaa>`, suivis des
  lignes produit **jusqu'au BL suivant**. Plusieurs BL par facture, **dates différentes**.
  Chaque ligne hérite du **numéro + date de son BL**.
- **Ligne produit** : `DÉSIGNATION` (peut être sur 2 lignes) / `CODE 13 chiffres` /
  `Qté  PUHT  %Remise  MontantRemise  PrixUnitaireNet  TauxTVA  MontantTotalHT`.
  - **Colonnes prix/remise/net/montant = FAUSSES** → ignorées (§8.2 cadrage).
  - On garde : désignation, code, qté, **TVA**, bl_numero, bl_date.
- **Piège TVA** : sur les lignes remisées il y a **deux pourcentages** (remise% puis Taux
  TVA). Le Taux TVA est l'un de **2,1 / 5,5 / 10 / 20** (légende : code 4=2.1, 5=5.5,
  6=20, 10=10). Le prompt doit extraire **le Taux TVA**, jamais la remise. Sur les lignes
  sans remise, il n'y a qu'un seul %.

---

## 3. Architecture

Réutilise l'infra Temps 1 (DB SQLite, `ClaudeExtractor`, `cout`, couche FastAPI). Cœur
pur testable + fine couche web.

| Module | Rôle |
|---|---|
| `app/temps2/schemas.py` | Modèles Pydantic de l'extraction LGO (`RetroExtrait`). |
| `app/temps2/ingest_retro.py` | Extraction LGO via `ClaudeExtractor` + prompt B. |
| `app/temps2/normalisation_dates.py` | `normaliser_date(s) -> date \| None` (formats variés → date). |
| `app/codes/correspondance.py` | Pont CIP↔EAN (table `correspondance_codes`). |
| `app/temps2/matching.py` | Passes 1-2 : résout le code d'une ligne contre le référentiel. |
| `app/temps2/calcul_prix.py` | « Dernier prix net ≤ date BL » pour un code résolu. |
| `app/temps2/traitement_retro.py` | Orchestration : extraction → matching → prix → stockage. |
| `app/db.py` | + tables `retro_documents`, `retro_lignes`, `correspondance_codes`. |
| `app/main.py` | Route `/retro` (import LGO, même UX compteur+coût) + vue des lignes. |
| `prompts/extraction_retro.txt` | Prompt B. |

---

## 4. Modèle de données (delta)

```sql
CREATE TABLE IF NOT EXISTS retro_documents (
  id INTEGER PRIMARY KEY,
  fichier TEXT,
  pharmacie_emettrice TEXT,
  pharmacie_destinataire TEXT,
  date_vente TEXT,
  numero TEXT,
  cout_estime REAL,
  ingere_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS retro_lignes (
  id INTEGER PRIMARY KEY,
  retro_id INTEGER REFERENCES retro_documents(id),
  designation TEXT, code TEXT, type_code TEXT,
  qte REAL, tva REAL,
  bl_numero TEXT, bl_date TEXT,
  code_resolu TEXT,
  prix_brut REAL, remise_pct REAL, prix_net REAL,
  ug REAL DEFAULT 0,
  passe_match INTEGER,            -- 1 | 2 (3-5 plus tard)
  score_match REAL,
  statut_ecart TEXT,              -- 'resolu' | 'rouge'
  valide_utilisateur INTEGER DEFAULT 0,
  saisie_manuelle INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS correspondance_codes (
  code_a TEXT, code_b TEXT,
  PRIMARY KEY (code_a, code_b)
);
```

Migration idempotente (mêmes `CREATE TABLE IF NOT EXISTS` + `_migrer` qu'au Temps 1).

---

## 5. Extraction LGO (prompt B) et schéma

### 5.1 Schéma (`app/temps2/schemas.py`)
```python
class RetroLigne(BaseModel):
    designation: str
    code: str | None
    type_code: str | None        # CIP13 | EAN13 | inconnu (déduit du contenu)
    qte: float | None
    tva: float | None            # Taux TVA (2.1 | 5.5 | 10 | 20), PAS la remise
    bl_numero: str | None
    bl_date: str | None          # date du Bon de livraison de la ligne

class RetroEntete(BaseModel):
    pharmacie_emettrice: str | None
    pharmacie_destinataire: str | None
    date_vente: str | None
    numero: str | None

class RetroExtrait(BaseModel):
    type_document: str           # attendu 'retro_lgo'
    entete: RetroEntete
    lignes: list[RetroLigne] = []
```

### 5.2 Prompt B (`prompts/extraction_retro.txt`) — règles impératives
- `type_document = "retro_lgo"`.
- En-tête : **émettrice** = société émettrice de la facture (en haut) ; **destinataire** =
  pharmacie acheteuse ; `date_vente`, `numero`.
- **Regroupement par BL** : à chaque `Bon livraison <num> du <date>`, rattacher à **toutes
  les lignes suivantes** (jusqu'au BL suivant) `bl_numero` et `bl_date`.
- Par ligne : `designation`, `code` (vrai code 13 — CIP13/EAN13), `qte`, **`tva` = le Taux
  TVA (2,1 / 5,5 / 10 / 20)**, jamais la remise.
- **Ignorer entièrement** PUHT, %Remise, Montant Remise, Prix unitaire Net, Montant Total
  HT (valeurs fausses).

Coût mesuré (réutilise `cout.cout_appel`), même mécanisme qu'au Temps 1.

---

## 6. Matching passes 1-2 (`matching.py`)

Pour une ligne (code, type_code), résoudre un `code_resolu` présent au référentiel :

| Passe | Méthode | `passe_match` |
|---|---|---|
| 1 | Code identique : il existe une entrée `referentiel_prix.code == ligne.code`. | 1 |
| 2 | Pont CIP↔EAN : `correspondance_codes` mappe `ligne.code` vers un code présent au référentiel. | 2 |

- `resoudre_code(conn, code) -> (code_resolu, passe) | (None, None)`.
- Passe 2 s'appuie sur `correspondance_codes` (table maintenue/semée ; vide au départ →
  passe 2 ne résout rien tant qu'elle n'est pas alimentée). Mécanisme testé.
- Passes 3-5 (désignation) **hors périmètre**.

---

## 7. Calcul prix « dernier prix ≤ date BL » (`calcul_prix.py`)

- `prix_a_date(conn, code_resolu, bl_date) -> ligne_referentiel | None` :
  1. Récupère toutes les entrées `referentiel_prix` du `code_resolu`.
  2. Normalise `date_facture` (référentiel) et `bl_date` via `normaliser_date`.
  3. Garde celles dont `date_facture ≤ bl_date`, prend la **plus récente** → son
     `prix_brut / remise_pct / prix_net`.
  4. Aucune entrée ≤ date BL → `None`.
- **Jamais fusionner** les occurrences : chaque ligne de rétrocession est chiffrée par
  **sa** date de BL ; un même produit sous deux BL de dates différentes peut recevoir deux
  prix différents.
- Comparaison en **Python** (les dates du référentiel sont stockées en texte, formats
  variés) : on ne migre pas les données, on normalise à la lecture.

### 7.1 Normalisation des dates (`normalisation_dates.py`)
`normaliser_date(s) -> datetime.date | None` accepte `jj/mm/aaaa`, `jj.mm.aaaa`,
`jj-mm-aaaa`, `aaaa-mm-jj` (et variantes 2 chiffres d'année → 20xx). Renvoie `None` si
illisible (la ligne part alors en `rouge`, jamais un prix au hasard).

---

## 8. Orchestration (`traitement_retro.py`)

`traiter_retro(conn, pdf, extractor, config) -> ResultatRetro` :
1. Extraction (prompt B) → `RetroExtrait`, coût mesuré.
2. Insert `retro_documents` (en-tête + cout_estime).
3. Pour chaque ligne :
   - `code_resolu, passe = matching.resoudre_code(conn, ligne.code)`.
   - si `code_resolu` : `ref = calcul_prix.prix_a_date(conn, code_resolu, ligne.bl_date)`.
     - `ref` trouvé → `statut_ecart='resolu'`, copie prix_brut/remise/net, `passe_match=passe`.
     - sinon → `statut_ecart='rouge'` (« prix manquant à cette date »).
   - sinon → `statut_ecart='rouge'` (« code introuvable au référentiel »).
   - Insert `retro_lignes`.
4. `ResultatRetro(retro_id, n_lignes, n_resolu, n_rouge, cout)`.

---

## 9. Interface web

- Route **`/retro`** : zone d'import des PDF LGO, **même UX** que `/` (ingestion fichier
  par fichier `POST /retro/ingest-un`, compteur **X/N**, barre, **coût** par fichier / lot /
  cumulé).
- Route **`/retro-lignes`** (ou vue par document) : tableau des lignes rétrocession avec
  désignation, code, qté, TVA, BL/date, prix net trouvé, **statut** coloré (resolu/rouge).
  Vue de consultation simple — le **tableau de résolution éditable** est le Temps 3.
- Navigation : ajouter « Rétrocession » au menu.

---

## 10. Stratégie de test

- **Normalisation dates** : `jj/mm/aaaa`, `jj.mm.aaaa`, ISO, année 2 chiffres, illisible→None.
- **Matching** : passe 1 (code présent), passe 2 (via `correspondance_codes`), introuvable→(None,None).
- **Calcul prix** : dernier ≤ date BL ; deux dates de référentiel pour un code ; aucune ≤
  date BL → None ; **multi-BL** (même produit, deux BL, deux prix).
- **Orchestration** (`traiter_retro`) avec `MockExtractor` + référentiel synthétique :
  ligne résolue, ligne rouge (code absent), ligne rouge (prix postérieur au BL),
  multi-lignes/multi-BL, coût remonté.
- **Extraction réelle** (marquée `integration`) sur la vraie facture LGO : vérifier
  en-tête (émettrice/destinataire), regroupement BL, TVA (≠ remise), codes.
- **Web** : `/retro` 200, `/retro/ingest-un` renvoie JSON (statut + coût), `/retro-lignes` 200.

---

## 11. Gestion d'erreurs

- PDF illisible / non-LGO → document en erreur, motif explicite, lot non interrompu.
- Échec API → idem Temps 1 (statut erreur côté UI ; le lot continue).
- Date de BL illisible → ligne `rouge` (« date BL illisible »), jamais de prix deviné.
- Aucune ligne de rétrocession n'est jamais chiffrée sans prix réel ≤ date BL.

---

## 12. Hors périmètre Temps 2 (rappel)

- Passes 3-5 (désignation, score, retour factures) — étape 9.
- Tableau de résolution éditable, validation orange/rouge, saisie manuelle (Temps 3).
- Édition de la facture de rétrocession PDF/Excel (Temps 4).

---

## 13. Critères d'acceptation Temps 2

1. Déposer une facture LGO via `/retro` produit un récap (lignes résolues / rouges) avec
   **compteur X/N + coût**, sans planter sur le format réel.
2. L'en-tête extrait identifie correctement **émettrice** et **destinataire**.
3. Les lignes sont **regroupées par BL** ; chaque ligne porte le **n° et la date de son BL**.
4. La **TVA** extraite est le Taux TVA (2,1/5,5/10/20), jamais la remise.
5. Le prix d'une ligne résolue est le **dernier prix net ≤ date du BL** ; un même produit
   sous deux BL de dates différentes peut recevoir deux prix différents.
6. Une ligne sans code au référentiel, ou sans prix ≤ date BL, est `rouge` (jamais chiffrée
   au hasard).
7. La normalisation des dates gère `jj/mm/aaaa`, `jj.mm.aaaa`, ISO ; illisible → `rouge`.
8. Le cœur (matching, calcul prix, normalisation) est couvert par des tests unitaires
   verts, sans appel API.
