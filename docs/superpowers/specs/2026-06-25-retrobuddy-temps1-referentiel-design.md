# RetroBuddy — Temps 1 : Socle + Référentiel prix — Design

> Spec du **premier sous-projet** de RetroBuddy. Découpage incrémental acté : on
> spec + build Temps 1, on valide sur de vrais PDF, puis on enchaîne Temps 2→4.
> Document de cadrage global de référence : `CADRAGE_RETROCESSION.md`.

- **Date** : 2026-06-25
- **Périmètre** : étapes 1→5 du §11 du cadrage.
- **Livrable** : déposer des factures labo PDF → classifier → extraire → valider →
  construire le **référentiel prix historisé** dans SQLite. Tout ce qui est douteux
  est signalé, jamais masqué.

---

## 1. Objectif et principe directeur

Construire la brique qui transforme un lot de **factures laboratoires (PDF)** en un
**référentiel prix historisé** réinterrogeable (par code, tous les prix nets avec leur
date). Ce référentiel est la source de vérité de coût pour toute la suite (Temps 2→4).

Principe directeur (hérité du cadrage) : **aucune erreur permise sur le montant.**
Tout ce qui n'est pas certain (checksum invalide, totaux qui ne réconcilient pas,
structure inhabituelle) est **signalé pour revue**, jamais ingéré en silence.

Non-objectif du Temps 1 : le matching LGO, la résolution d'écarts et la facture de
sortie (Temps 2→4). Le calcul « dernier prix ≤ date BL » est un usage du référentiel
qui arrive au Temps 2 ; le Temps 1 se contente de **stocker l'historique complet**
(`code` + `date_facture`) pour le rendre possible.

---

## 2. Architecture

**Principe** : un **cœur Python pur, testable unitairement** (sans appel API), enveloppé
par une **fine couche web FastAPI**. Chaque règle métier est isolée et testée seule.

### 2.1 Modules (un rôle = un fichier)

| Module | Rôle | Dépend de |
|---|---|---|
| `app/db.py` | Schéma SQLite + connexion. | sqlite3 (stdlib) |
| `app/config.py` | Chargement `config.local.yaml` (clé API, seuils). | pyyaml |
| `app/temps1/pdf_reader.py` | Charge un PDF → bloc `document` base64 + métadonnées (nb pages, taille). | base64, pathlib |
| `app/temps1/extraction_ia.py` | Interface `Extractor` + `ClaudeExtractor` (Sonnet, prompt A, schéma Pydantic) + `MockExtractor`. | anthropic, pydantic |
| `app/temps1/classifier.py` | §4 — exploite `type_document` ; route facture / avoir / abonnement / relevé / autre. | (modèles Pydantic) |
| `app/codes/checksum.py` | Clés CIP13 (préfixe 34009) & EAN13 ; distingue code interne d'un vrai code 13. | — |
| `app/temps1/filtres.py` | §3.2 — sélection des lignes valides. | checksum |
| `app/temps1/garde_fous.py` | §5 — checksum, net affiché, réconciliation totaux, code interne ≠ CIP. | checksum |
| `app/temps1/referentiel.py` | Écrit les lignes valides dans `referentiel_prix` (historisé). | db |
| `app/temps1/pipeline.py` | Orchestration : pdf → extraction → classification → garde-fous → filtres → référentiel. | tous les ci-dessus |
| `app/main.py` | FastAPI : page d'import + vues référentiel / factures ignorées / en revue. | fastapi, pipeline, db |

Modèles de données Pydantic partagés (schéma de sortie de l'extraction) : `app/temps1/schemas.py`.

### 2.2 Flux nominal

```
PDF labo
  │  pdf_reader → bloc document base64
  ▼
ClaudeExtractor (1 appel IA = classifie + extrait, prompt A, sortie structurée)
  │  → objet FactureExtraite validé (Pydantic)
  ▼
classifier
  ├─ type ≠ facture_marchandise ──► facture enregistrée "ignorée" (raison), STOP
  ▼
garde_fous (checksum, totaux, net affiché, code interne)
  ├─ totaux ne réconcilient pas / structure inhabituelle ──► facture "en revue", STOP
  ▼
filtres (§3.2) — retient les lignes valides, ignore UG / RFA / remises globales
  ▼
referentiel — upsert (code, date_facture) → prix brut/remise/net + designation + facture_id
  │
  ▼
facture marquée "ingérée"
```

### 2.3 Escalade modèle

- Extraction par défaut : **Sonnet 4.6** (`claude-sonnet-4-6`).
- Si les garde-fous d'une facture **échouent** (checksum lignes KO en nombre, totaux
  hors seuil), `pipeline` relance **une** extraction en **Opus 4.8**
  (`claude-opus-4-8`) sur le même PDF. Si Opus réconcilie → ingérée ; sinon → **en revue**.
- L'escalade est portée par `ClaudeExtractor` (paramètre `model`) ; `pipeline` décide.

---

## 3. Modèle de données (sous-ensemble Temps 1)

SQLite, fichier `data/retrocession.db`. Tables créées par `db.py` (idempotent).

```sql
CREATE TABLE IF NOT EXISTS factures (
  id INTEGER PRIMARY KEY,
  fichier TEXT,
  labo TEXT,
  numero_facture TEXT,
  date_facture DATE,
  type_document TEXT,              -- facture_marchandise | avoir | abonnement_service | releve | autre
  total_affiche REAL,
  total_calcule REAL,
  statut TEXT,                     -- 'ingeree' | 'ignoree' | 'en_revue'
  motif TEXT,                      -- raison d'ignore/revue (lisible)
  modele_extraction TEXT,          -- 'sonnet-4.6' | 'opus-4.8'
  ingere_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lignes_facture (
  id INTEGER PRIMARY KEY,
  facture_id INTEGER REFERENCES factures(id),
  code TEXT, type_code TEXT, code_interne TEXT,
  designation TEXT,
  qte REAL, qte_gratuite REAL,
  prix_brut REAL, remise_pct REAL, prix_net REAL,
  montant_ht REAL, tva REAL,
  checksum_ok BOOLEAN,
  valide BOOLEAN                   -- retenue par les filtres §3.2
);

CREATE TABLE IF NOT EXISTS referentiel_prix (
  code TEXT, date_facture DATE,
  prix_brut REAL, remise_pct REAL, prix_net REAL,
  designation TEXT, facture_id INTEGER,
  PRIMARY KEY (code, date_facture)
);

CREATE TABLE IF NOT EXISTS abreviations_labo (
  abrev TEXT PRIMARY KEY, complet TEXT
);
```

Notes :
- `referentiel_prix` garde **l'historique complet** (clé `code`+`date_facture`), jamais
  seulement le dernier prix — indispensable pour « dernier prix ≤ date BL » (Temps 2).
- `abreviations_labo` est créée dès le Temps 1 (table de normalisation maintenue à la
  main) mais n'est exploitée qu'au Temps 2 (matching désignation). Aucun remplissage requis ici.
- Sur clé `(code, date_facture)` déjà présente : on **remplace** par la dernière ingestion
  (réingestion idempotente d'une même facture).

---

## 4. Extraction IA (prompt A) et schéma de sortie

### 4.1 Sortie structurée (Pydantic → `output_config.format`)

L'appel utilise une **sortie structurée** : le modèle est contraint au schéma, on récupère
du JSON validé (pas de parsing fragile). Schéma (`schemas.py`) :

```python
class LigneFacture(BaseModel):
    code: str | None                 # vrai CIP13/EAN13, jamais interne
    type_code: str | None            # 'CIP13' | 'EAN13' | 'interne' | 'inconnu'
    code_interne: str | None
    designation: str
    qte: float | None
    qte_gratuite: float = 0
    prix_brut: float | None
    remise_pct: float | None
    remises_detail: list[float] = []  # multi-remises éventuelles
    prix_net: float | None            # AFFICHÉ, non recalculé
    montant_ht: float | None
    tva: float | None

class EnteteFacture(BaseModel):
    labo: str | None
    numero_facture: str | None
    date_facture: str | None          # ISO si possible
    total_ht_affiche: float | None

class FactureExtraite(BaseModel):
    type_document: str                # cf. §4 cadrage
    entete: EnteteFacture
    lignes: list[LigneFacture]
```

### 4.2 Prompt A (`prompts/extraction_facture.txt`)

Règles imposées au modèle (cf. §8.1 cadrage) :
- **Classifier d'abord** le document (facture_marchandise / avoir / abonnement_service /
  releve / autre).
- Renvoyer le **prix net AFFICHÉ**, jamais reconstruit depuis une seule remise.
- Distinguer **code interne** et **CIP/EAN** : `code` = le vrai code 13 ; le code interne
  va dans `code_interne`.
- Ne pas extraire les récapitulatifs tarifaires (texte libre sans codes/quantités).
- « UG » dans une désignation = nom commercial, **pas** une unité gratuite.

Le prompt système (stable) est **mis en cache** (prompt caching) pour réduire le coût sur
un lot de factures.

### 4.3 Interface Extractor (testabilité)

```python
class Extractor(Protocol):
    def extraire(self, pdf: PdfDocument, model: str) -> FactureExtraite: ...

class ClaudeExtractor:   # appelle l'API
class MockExtractor:     # renvoie une FactureExtraite depuis une fixture (tests)
```

---

## 5. Règles métier

### 5.1 Classification (§4)
| type_document | Action |
|---|---|
| facture_marchandise | Traiter |
| avoir | Ignorer (statut `ignoree`, motif « avoir ») |
| abonnement_service | Ignorer |
| releve | Ignorer |
| autre / grossiste | Ignorer (V1) |

Décision V1 : les avoirs n'impactent pas le référentiel.

### 5.2 Filtres lignes valides (§3.2)
- **Retenir** : `prix_brut > 0` **et** `remise_pct < 100` **et** `prix_net > 0` **et** code rattaché.
- **Ignorer** : UG (y compris ligne séparée « remise 100 % » / net = 0), RFA, remises
  globales/exceptionnelles non rattachées à un produit.
- Les lignes ignorées sont stockées (`valide = 0`) pour traçabilité, mais n'alimentent pas
  le référentiel.

### 5.3 Garde-fous (§5)
1. **Checksum codes** : clé CIP13 (préfixe 34009) et EAN13. Invalide → ligne non rapprochée,
   `checksum_ok = 0`, signalée.
2. **Net affiché** : on valide contre le PU net affiché, **pas** de reconstruction depuis
   une seule remise (cas multi-remises : Pierre Fabre, Perrigo, PiLeJe).
3. **Cohérence totaux** : somme des `montant_ht` retenus ≈ `total_ht_affiche`.
   Écart > seuil (configurable, défaut **1 %** ou 0,02 € absolu) → facture **en revue**.
4. **Code interne ≠ CIP/EAN** : cibler le vrai code 13 chiffres (cas AbbVie 20007519,
   Fresenius 107621 = codes internes).

### 5.4 Checksum (`codes/checksum.py`)
- `cip13_valide(code)` : 13 chiffres, préfixe `34009`, clé de contrôle GTIN-13
  (somme pondérée 1/3 des 12 premiers chiffres, modulo 10).
- `ean13_valide(code)` : 13 chiffres, même clé de contrôle GTIN-13.
- `type_de_code(code)` : déduit `CIP13` / `EAN13` / `interne` / `inconnu` du **contenu**
  du code (clé), pas de son intitulé (cf. Arkopharma : EAN sous libellé « CIP/ACL »).

---

## 6. Interface web minimale (FastAPI)

Volontairement sobre au Temps 1 — le tableau type Excel riche arrive au Temps 3.

- `GET /` : page d'accueil avec **zone de dépôt** de PDF labo (multi-fichiers).
- `POST /ingest` : lance le pipeline sur les fichiers déposés, renvoie un récap
  (n ingérées / n ignorées / n en revue).
- `GET /referentiel` : tableau du référentiel (code, date, designation, net) — filtrable.
- `GET /factures` : liste des factures avec statut + motif ; les **en revue** et
  **ignorées** sont visibles en clair (jamais masquées).
- Export/import de la base (`data/retrocession.db`) : un bouton **exporter** (télécharge le
  fichier) et **importer** (remplace la base) — pour partager le référentiel entre confrères.

Templates HTML simples (`app/ui/`), pas de framework front lourd.

---

## 7. Configuration et secrets

- `config.local.yaml` (**gitignored**) : `anthropic_api_key`, `model_defaut`,
  `model_escalade`, `seuil_reconciliation`.
- `config.example.yaml` (versionné) : même structure, valeurs factices.
- `.gitignore` dès l'initialisation : `config.local.yaml`, `data/*.db`, `__pycache__/`,
  `.venv/`, `data/samples/`.
- La clé n'est jamais écrite dans un fichier versionné ni loggée.

---

## 8. Stratégie de test (TDD)

- **Cœur métier testé sans API** via `MockExtractor` + fixtures JSON (`tests/fixtures/`) :
  - `checksum` : CIP13/EAN13 valides et invalides, codes internes, cas Arkopharma.
  - `filtres` : UG ligne séparée, remise 100 %, RFA, multi-remises, piège « +1UG » dans le nom.
  - `garde_fous` : totaux qui réconcilient / pas, net affiché vs reconstruit.
  - `classifier` : chaque `type_document` route correctement.
  - `referentiel` : historisation (même code, deux dates → deux entrées), idempotence.
- **Tests d'intégration** (marqués `@pytest.mark.integration`, désactivés par défaut) :
  pipeline complet sur les **vrais PDF** de `data/samples/` avec la vraie clé API.
- Cible : chaque module a ses tests avant son implémentation (red → green → refactor).

---

## 9. Gestion d'erreurs

- PDF illisible / non-PDF → facture `en_revue`, motif explicite, pipeline continue sur les autres.
- Échec API (réseau, rate limit) : retries SDK par défaut ; échec persistant → `en_revue`,
  motif « extraction indisponible ».
- Sortie structurée invalide (rare, schéma garanti) → `en_revue`, motif « extraction non conforme ».
- Aucune facture n'est jamais ingérée partiellement : soit `ingeree` complète, soit
  `ignoree`/`en_revue`.

---

## 10. Coût (rappel cadrage §12)

Sonnet 4.6 ($3/$15 par M tokens), ~0,03 $/facture standard, ~0,015 $ en Batch.
Escalade Opus 4.8 ($5/$25) seulement sur les factures signalées → surcoût marginal.
Prompt caching sur le prompt système → réduction supplémentaire sur un lot.

---

## 11. Hors périmètre Temps 1 (rappel)

- Matching LGO, passes 1→6, normalisation désignations (Temps 2).
- Calcul « dernier prix ≤ date BL » (Temps 2 — le référentiel est prêt à le servir).
- Interface de résolution d'écarts type Excel, compteurs, couleurs (Temps 3).
- Édition de la facture de rétrocession, PDF/Excel de sortie (Temps 4).

---

## 12. Critères d'acceptation Temps 1

1. Déposer un dossier de factures labo PDF via la page web produit un récap
   (ingérées / ignorées / en revue) sans planter sur les cas pièges du lot réel.
2. Le référentiel contient, par code, **tous** les prix nets avec leur date (historisé).
3. Aucune facture dont les totaux ne réconcilient pas n'apparaît comme « ingérée ».
4. Avoirs, abonnements, relevés sont classés « ignorés » et n'impactent pas le référentiel.
5. UG, RFA et remises globales sont exclues du référentiel ; le piège « +1UG » dans un nom
   commercial n'est pas traité comme une UG.
6. Le cœur métier est couvert par des tests unitaires verts, sans appel API.
7. La clé API n'est dans aucun fichier versionné.
