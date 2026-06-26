# RetroBuddy — Temps 2 (Ingestion LGO + Matching + Calcul prix) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingérer une facture de vente rétrocession du LGO (PDF), rapprocher chaque ligne du référentiel prix par code (passes 1-2), et chiffrer chaque ligne au dernier prix net ≤ date de son BL — tout ce qui n'est pas rapproché étant signalé en rouge.

**Architecture:** Réutilise l'infra Temps 1 (SQLite, `ClaudeExtractor` rendu générique, module `cout`, couche FastAPI avec UX compteur X/N + coût). Cœur pur testable (normalisation dates, matching, calcul prix, orchestration) + extraction Claude (PDF natif + sortie structurée Pydantic) + fine couche web `/retro`.

**Tech Stack:** Python 3.13, SQLite (`sqlite3`), `anthropic`, `pydantic` v2, `fastapi`, `jinja2`, `pytest`.

**Spec de référence :** `docs/superpowers/specs/2026-06-26-retrobuddy-temps2-matching-design.md`.

---

## Conventions

- Chemins relatifs à `C:\Users\pharma01\Desktop\RetroBuddy`. Python/pytest via `.venv/Scripts/python`.
- Tests unitaires : aucun appel réseau. Un test d'intégration (Task 7) marqué `integration`, désactivé par défaut.
- Le référentiel prix (table `referentiel_prix`) est construit au Temps 1 ; ici on le lit.

---

### Task 1: Tables Temps 2 (`db.py`)

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Écrire le test (ajout à `tests/test_db.py`)**

Ajouter cette fonction à la fin de `tests/test_db.py` :

```python
def test_init_db_cree_les_tables_temps2(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    noms = _tables(conn)
    assert {"retro_documents", "retro_lignes", "correspondance_codes"} <= noms
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_db.py::test_init_db_cree_les_tables_temps2 -v`
Expected: FAIL (tables absentes).

- [ ] **Step 3: Ajouter les tables au `SCHEMA` de `app/db.py`**

Dans `app/db.py`, juste avant la ligne `CREATE TABLE IF NOT EXISTS abreviations_labo`, insérer :

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
  passe_match INTEGER,
  score_match REAL,
  statut_ecart TEXT,
  valide_utilisateur INTEGER DEFAULT 0,
  saisie_manuelle INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS correspondance_codes (
  code_a TEXT, code_b TEXT,
  PRIMARY KEY (code_a, code_b)
);
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_db.py -v`
Expected: PASS (tous, y compris le nouveau).

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat(temps2): tables retro_documents, retro_lignes, correspondance_codes"
```

---

### Task 2: Normalisation des dates (`temps2/normalisation_dates.py`)

**Files:**
- Create: `app/temps2/__init__.py`
- Create: `app/temps2/normalisation_dates.py`
- Test: `tests/test_normalisation_dates.py`

- [ ] **Step 1: Créer le package**

Créer le fichier vide `app/temps2/__init__.py`.

- [ ] **Step 2: Écrire le test**

Create `tests/test_normalisation_dates.py`:

```python
import datetime

from app.temps2.normalisation_dates import normaliser_date


def test_jj_mm_aaaa():
    assert normaliser_date("01/08/2025") == datetime.date(2025, 8, 1)


def test_jj_point_mm_point_aaaa():
    assert normaliser_date("02.03.2026") == datetime.date(2026, 3, 2)


def test_iso():
    assert normaliser_date("2026-03-02") == datetime.date(2026, 3, 2)


def test_annee_2_chiffres():
    assert normaliser_date("31/08/25") == datetime.date(2025, 8, 31)


def test_illisible_renvoie_none():
    assert normaliser_date("le 3 mars") is None


def test_none_renvoie_none():
    assert normaliser_date(None) is None
```

- [ ] **Step 3: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_normalisation_dates.py -v`
Expected: FAIL (module absent).

- [ ] **Step 4: Implémenter `app/temps2/normalisation_dates.py`**

```python
import datetime
import re


def normaliser_date(s):
    """Parse jj/mm/aaaa, jj.mm.aaaa, jj-mm-aaaa, aaaa-mm-jj (et année 2 chiffres).

    Renvoie une datetime.date, ou None si illisible.
    """
    if not s:
        return None
    m = re.match(r"^\s*(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})\s*$", str(s))
    if not m:
        return None
    a, b, c = m.groups()
    if len(a) == 4:                      # aaaa-mm-jj
        annee, mois, jour = int(a), int(b), int(c)
    else:                                # jj-mm-aaaa
        jour, mois, annee = int(a), int(b), int(c)
        if annee < 100:
            annee += 2000
    try:
        return datetime.date(annee, mois, jour)
    except ValueError:
        return None
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_normalisation_dates.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add app/temps2/__init__.py app/temps2/normalisation_dates.py tests/test_normalisation_dates.py
git commit -m "feat(temps2): normalisation des dates (formats variés -> date)"
```

---

### Task 3: Schéma d'extraction LGO (`temps2/schemas.py`)

**Files:**
- Create: `app/temps2/schemas.py`
- Test: `tests/test_schemas_retro.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_schemas_retro.py`:

```python
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
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_schemas_retro.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/temps2/schemas.py`**

```python
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
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_schemas_retro.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add app/temps2/schemas.py tests/test_schemas_retro.py
git commit -m "feat(temps2): schémas Pydantic d'extraction LGO (retro)"
```

---

### Task 4: Pont CIP↔EAN (`codes/correspondance.py`)

**Files:**
- Create: `app/codes/correspondance.py`
- Test: `tests/test_correspondance.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_correspondance.py`:

```python
from app.codes.correspondance import resoudre_via_correspondance
from app.db import get_connection, init_db


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def test_resout_dans_les_deux_sens(tmp_path):
    conn = _conn(tmp_path)
    conn.execute("INSERT INTO correspondance_codes (code_a, code_b) VALUES (?, ?)",
                 ("3400930000007", "4006381333931"))
    conn.commit()
    assert resoudre_via_correspondance(conn, "3400930000007") == "4006381333931"
    assert resoudre_via_correspondance(conn, "4006381333931") == "3400930000007"


def test_inconnu_renvoie_none(tmp_path):
    conn = _conn(tmp_path)
    assert resoudre_via_correspondance(conn, "9999999999999") is None
    assert resoudre_via_correspondance(conn, None) is None
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_correspondance.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/codes/correspondance.py`**

```python
def resoudre_via_correspondance(conn, code):
    """Renvoie un code équivalent (pont CIP<->EAN) via correspondance_codes, ou None."""
    if not code:
        return None
    row = conn.execute(
        "SELECT code_b AS autre FROM correspondance_codes WHERE code_a = ? "
        "UNION "
        "SELECT code_a AS autre FROM correspondance_codes WHERE code_b = ?",
        (code, code),
    ).fetchone()
    return row["autre"] if row else None
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_correspondance.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/codes/correspondance.py tests/test_correspondance.py
git commit -m "feat(temps2): pont CIP<->EAN via table correspondance_codes"
```

---

### Task 5: Matching passes 1-2 (`temps2/matching.py`)

**Files:**
- Create: `app/temps2/matching.py`
- Test: `tests/test_matching.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_matching.py`:

```python
from app.db import get_connection, init_db
from app.temps2.matching import resoudre_code


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_net) VALUES (?, ?, ?)",
        (code, "2025-08-01", 5.0))
    conn.commit()


def test_passe1_code_identique(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007")
    assert resoudre_code(conn, "3400930000007") == ("3400930000007", 1)


def test_passe2_pont_cip_ean(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "4006381333931")  # le référentiel a l'EAN
    conn.execute("INSERT INTO correspondance_codes (code_a, code_b) VALUES (?, ?)",
                 ("3400930000007", "4006381333931"))
    conn.commit()
    # la ligne LGO porte le CIP -> résolu via le pont vers l'EAN présent
    assert resoudre_code(conn, "3400930000007") == ("4006381333931", 2)


def test_introuvable(tmp_path):
    conn = _conn(tmp_path)
    assert resoudre_code(conn, "3400930000007") == (None, None)
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_matching.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/temps2/matching.py`**

```python
from app.codes.correspondance import resoudre_via_correspondance


def _code_au_referentiel(conn, code):
    if not code:
        return False
    return conn.execute(
        "SELECT 1 FROM referentiel_prix WHERE code = ? LIMIT 1", (code,)
    ).fetchone() is not None


def resoudre_code(conn, code):
    """Passe 1 (code identique) puis passe 2 (pont CIP<->EAN).

    Retourne (code_resolu, passe) ou (None, None).
    """
    if _code_au_referentiel(conn, code):
        return (code, 1)
    autre = resoudre_via_correspondance(conn, code)
    if autre and _code_au_referentiel(conn, autre):
        return (autre, 2)
    return (None, None)
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_matching.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps2/matching.py tests/test_matching.py
git commit -m "feat(temps2): matching passes 1-2 (code identique + pont CIP/EAN)"
```

---

### Task 6: Calcul prix ≤ date BL (`temps2/calcul_prix.py`)

**Files:**
- Create: `app/temps2/calcul_prix.py`
- Test: `tests/test_calcul_prix.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_calcul_prix.py`:

```python
from app.db import get_connection, init_db
from app.temps2.calcul_prix import prix_a_date


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code, date_facture, prix_net):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_brut, remise_pct, prix_net) "
        "VALUES (?, ?, ?, ?, ?)",
        (code, date_facture, prix_net + 1, 10.0, prix_net))
    conn.commit()


def test_dernier_prix_avant_date_bl(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "01/07/2025", 5.0)
    _ref(conn, "C", "05/08/2025", 4.5)
    r = prix_a_date(conn, "C", "10/08/2025")   # les deux <= BL, on prend le + récent
    assert r["prix_net"] == 4.5


def test_ignore_les_prix_posterieurs_au_bl(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "01/07/2025", 5.0)
    _ref(conn, "C", "05/08/2025", 4.5)
    r = prix_a_date(conn, "C", "15/07/2025")   # seul le 01/07 <= BL
    assert r["prix_net"] == 5.0


def test_aucun_prix_avant_le_bl(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "05/08/2025", 4.5)
    assert prix_a_date(conn, "C", "01/06/2025") is None


def test_bl_date_illisible(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C", "05/08/2025", 4.5)
    assert prix_a_date(conn, "C", "le 5 août") is None
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_calcul_prix.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/temps2/calcul_prix.py`**

```python
from app.temps2.normalisation_dates import normaliser_date


def prix_a_date(conn, code_resolu, bl_date):
    """Dernier prix net du référentiel pour `code_resolu` avec date_facture <= bl_date.

    Comparaison en Python (dates du référentiel en texte, formats variés).
    Retourne un dict {date_facture, prix_brut, remise_pct, prix_net} ou None.
    """
    d_bl = normaliser_date(bl_date)
    if d_bl is None or not code_resolu:
        return None
    rows = conn.execute(
        "SELECT date_facture, prix_brut, remise_pct, prix_net "
        "FROM referentiel_prix WHERE code = ?",
        (code_resolu,),
    ).fetchall()
    candidats = []
    for r in rows:
        d = normaliser_date(r["date_facture"])
        if d is not None and d <= d_bl:
            candidats.append((d, r))
    if not candidats:
        return None
    _, r = max(candidats, key=lambda x: x[0])
    return {"date_facture": r["date_facture"], "prix_brut": r["prix_brut"],
            "remise_pct": r["remise_pct"], "prix_net": r["prix_net"]}
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_calcul_prix.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps2/calcul_prix.py tests/test_calcul_prix.py
git commit -m "feat(temps2): calcul prix dernier <= date BL (avec normalisation dates)"
```

---

### Task 7: Extracteur générique + prompt B + test d'intégration

**Files:**
- Modify: `app/temps1/extraction_ia.py`
- Create: `prompts/extraction_retro.txt`
- Test: `tests/test_retro_integration.py`

> On généralise le `ClaudeExtractor` existant pour accepter un `output_format` (défaut
> `FactureExtraite`), au lieu de dupliquer l'appel API. Le Temps 1 n'est pas affecté
> (paramètre par défaut). Pour la rétro, on l'instancie avec `RetroExtrait` + prompt B.

- [ ] **Step 1: Généraliser `ClaudeExtractor` dans `app/temps1/extraction_ia.py`**

Remplacer le `__init__` et le début de `extraire` de `ClaudeExtractor` par :

```python
    def __init__(self, api_key: str, prompt_path="prompts/extraction_facture.txt",
                 output_format=FactureExtraite):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._prompt = Path(prompt_path).read_text(encoding="utf-8")
        self._output_format = output_format
        self.dernier_cout = 0.0
        self.cout_cumule = 0.0

    def extraire(self, pdf: PdfDocument, model: str):
        resp = self._client.messages.parse(
```

Puis, dans le corps de `extraire`, remplacer la ligne `output_format=FactureExtraite,` par :

```python
            output_format=self._output_format,
```

- [ ] **Step 2: Vérifier que les tests Temps 1 passent toujours**

Run: `.venv/Scripts/python -m pytest tests/test_extraction_ia.py tests/test_pipeline.py -v`
Expected: PASS (le défaut `FactureExtraite` préserve le comportement Temps 1).

- [ ] **Step 3: Créer le prompt B `prompts/extraction_retro.txt`**

```
Tu es un extracteur de factures de vente rétrocession éditées par un LGO (LGPI).
Tu reçois la facture en PDF et tu produis un JSON STRICT conforme au schéma imposé.

RÈGLES IMPÉRATIVES :
1. type_document = "retro_lgo".
2. EN-TÊTE :
   - pharmacie_emettrice = la société qui ÉMET la facture (bloc société en haut).
   - pharmacie_destinataire = la pharmacie ACHETEUSE (bloc destinataire).
   - date_vente = la date de la vente rétrocession ; numero = le numéro de facture.
3. REGROUPEMENT PAR BL : le document liste des en-têtes "Bon livraison <numéro> du
   <date>". Chaque en-tête s'applique à TOUTES les lignes produit qui suivent, jusqu'au
   prochain "Bon livraison". Reporter sur chaque ligne son bl_numero et sa bl_date.
4. Par ligne produit : designation, code (le vrai code à 13 chiffres : CIP13 préfixe
   34009, ou EAN13), type_code, qte, et tva.
5. TVA : c'est le TAUX TVA de la colonne "Taux TVA" (l'une des valeurs 2,1 / 5,5 / 10 /
   20). ATTENTION : sur les lignes remisées il y a DEUX pourcentages — le premier est la
   REMISE, le second est le TAUX TVA. Ne JAMAIS confondre : tva = le Taux TVA.
6. IGNORER ENTIÈREMENT les colonnes PUHT, % Remise, Montant Remise, Prix unitaire Net,
   Montant Total HT : ce sont des valeurs FAUSSES, ne pas les extraire.

Réponds UNIQUEMENT avec le JSON conforme au schéma fourni.
```

- [ ] **Step 4: Créer le test d'intégration `tests/test_retro_integration.py`**

```python
"""Test d'intégration LGO (vraie API). Lancer avec :
    .venv/Scripts/python -m pytest -m integration
Nécessite config.local.yaml (clé) et un PDF dans data/samples/factures_lgo/.
"""
from pathlib import Path

import pytest

from app.config import charger_config
from app.temps1.extraction_ia import ClaudeExtractor
from app.temps1.pdf_reader import lire_pdf
from app.temps2.schemas import RetroExtrait

SAMPLES = Path("data/samples/factures_lgo")


@pytest.mark.integration
def test_extraction_lgo_reelle():
    cfg = charger_config()
    if not cfg.get("anthropic_api_key"):
        pytest.skip("clé API absente")
    pdfs = sorted(SAMPLES.glob("*.pdf")) if SAMPLES.exists() else []
    if not pdfs:
        pytest.skip("aucun PDF dans data/samples/factures_lgo/")

    ex = ClaudeExtractor(cfg["anthropic_api_key"],
                         prompt_path="prompts/extraction_retro.txt",
                         output_format=RetroExtrait)
    retro = ex.extraire(lire_pdf(pdfs[0]), cfg["model_defaut"])

    assert retro.type_document == "retro_lgo"
    assert retro.lignes, "au moins une ligne extraite"
    # chaque ligne porte un BL et une TVA plausible
    l = retro.lignes[0]
    assert l.bl_date is not None
    assert l.tva in (2.1, 5.5, 10.0, 20.0)
```

- [ ] **Step 5: Vérifier que le test d'intégration est désélectionné par défaut**

Run: `.venv/Scripts/python -m pytest -v`
Expected: tous les unitaires passent ; `test_extraction_lgo_reelle` deselected.

- [ ] **Step 6: Commit**

```bash
git add app/temps1/extraction_ia.py prompts/extraction_retro.txt tests/test_retro_integration.py
git commit -m "feat(temps2): ClaudeExtractor générique (output_format) + prompt B"
```

---

### Task 8: Orchestration rétro (`temps2/traitement_retro.py`)

**Files:**
- Create: `app/temps2/traitement_retro.py`
- Test: `tests/test_traitement_retro.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_traitement_retro.py`:

```python
from app.db import get_connection, init_db
from app.temps1.extraction_ia import MockExtractor
from app.temps1.pdf_reader import PdfDocument
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne
from app.temps2.traitement_retro import traiter_retro

CFG = {"model_defaut": "claude-sonnet-4-6", "model_escalade": "claude-opus-4-8"}


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code, date_facture, prix_net):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_brut, remise_pct, prix_net) "
        "VALUES (?, ?, ?, ?, ?)",
        (code, date_facture, prix_net + 1, 10.0, prix_net))
    conn.commit()


def _pdf():
    return PdfDocument(nom="retro.pdf", base64="", taille_octets=0)


def _retro(lignes):
    return RetroExtrait(
        type_document="retro_lgo",
        entete=RetroEntete(pharmacie_emettrice="SERALY",
                           pharmacie_destinataire="CENON",
                           date_vente="22/09/2025", numero="N1"),
        lignes=lignes)


def _ligne(code, bl_date, bl_numero="28476"):
    return RetroLigne(designation="X", code=code, type_code="CIP13", qte=1,
                      tva=10.0, bl_numero=bl_numero, bl_date=bl_date)


def test_ligne_resolue(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007", "01/08/2025", 4.5)
    retro = _retro([_ligne("3400930000007", "10/08/2025")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_resolu == 1
    assert res.n_rouge == 0
    r = conn.execute("SELECT statut_ecart, prix_net, code_resolu, passe_match "
                     "FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "resolu"
    assert r["prix_net"] == 4.5
    assert r["code_resolu"] == "3400930000007"
    assert r["passe_match"] == 1


def test_ligne_rouge_code_absent(tmp_path):
    conn = _conn(tmp_path)
    retro = _retro([_ligne("3400930000007", "10/08/2025")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_rouge == 1
    r = conn.execute("SELECT statut_ecart, prix_net FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "rouge"
    assert r["prix_net"] is None


def test_ligne_rouge_prix_posterieur_au_bl(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007", "20/08/2025", 4.5)   # prix APRÈS le BL
    retro = _retro([_ligne("3400930000007", "10/08/2025")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_rouge == 1
    assert conn.execute("SELECT statut_ecart FROM retro_lignes").fetchone()["statut_ecart"] == "rouge"


def test_multi_bl_meme_produit_deux_prix(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930000007", "01/07/2025", 5.0)
    _ref(conn, "3400930000007", "05/08/2025", 4.5)
    retro = _retro([
        _ligne("3400930000007", "15/07/2025", bl_numero="A"),   # -> 5.0
        _ligne("3400930000007", "10/08/2025", bl_numero="B"),   # -> 4.5
    ])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_resolu == 2
    prix = [r["prix_net"] for r in conn.execute(
        "SELECT prix_net FROM retro_lignes ORDER BY bl_numero")]
    assert prix == [5.0, 4.5]


class _ExtracteurAvecCout:
    def __init__(self, retro, cout):
        self._retro = retro
        self.dernier_cout = cout

    def extraire(self, pdf, model):
        return self._retro


def test_cout_remonte(tmp_path):
    conn = _conn(tmp_path)
    retro = _retro([_ligne("3400930000007", "10/08/2025")])
    res = traiter_retro(conn, _pdf(), _ExtracteurAvecCout(retro, 0.04), CFG)
    assert res.cout == 0.04
    c = conn.execute("SELECT cout_estime FROM retro_documents").fetchone()["cout_estime"]
    assert c == 0.04
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_traitement_retro.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/temps2/traitement_retro.py`**

```python
from dataclasses import dataclass

from app.temps2 import calcul_prix, matching


@dataclass
class ResultatRetro:
    retro_id: int
    n_lignes: int
    n_resolu: int
    n_rouge: int
    cout: float = 0.0


def traiter_retro(conn, pdf, extractor, config) -> ResultatRetro:
    retro = extractor.extraire(pdf, config["model_defaut"])
    cout = getattr(extractor, "dernier_cout", 0.0)

    cur = conn.execute(
        """
        INSERT INTO retro_documents
          (fichier, pharmacie_emettrice, pharmacie_destinataire, date_vente, numero, cout_estime)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (pdf.nom, retro.entete.pharmacie_emettrice, retro.entete.pharmacie_destinataire,
         retro.entete.date_vente, retro.entete.numero, cout),
    )
    retro_id = cur.lastrowid

    n_resolu = n_rouge = 0
    for l in retro.lignes:
        code_resolu, passe = matching.resoudre_code(conn, l.code)
        prix = calcul_prix.prix_a_date(conn, code_resolu, l.bl_date) if code_resolu else None
        if prix is not None:
            statut, n_resolu = "resolu", n_resolu + 1
            pb, rp, pn = prix["prix_brut"], prix["remise_pct"], prix["prix_net"]
        else:
            statut, n_rouge = "rouge", n_rouge + 1
            pb = rp = pn = None
        conn.execute(
            """
            INSERT INTO retro_lignes
              (retro_id, designation, code, type_code, qte, tva, bl_numero, bl_date,
               code_resolu, prix_brut, remise_pct, prix_net, passe_match, statut_ecart)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (retro_id, l.designation, l.code, l.type_code, l.qte, l.tva, l.bl_numero,
             l.bl_date, code_resolu, pb, rp, pn, passe, statut),
        )
    conn.commit()
    return ResultatRetro(retro_id, len(retro.lignes), n_resolu, n_rouge, cout)
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_traitement_retro.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lancer toute la suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tous les unitaires verts ; intégration deselected.

- [ ] **Step 6: Commit**

```bash
git add app/temps2/traitement_retro.py tests/test_traitement_retro.py
git commit -m "feat(temps2): orchestration rétro (extraction -> matching -> prix -> stockage)"
```

---

### Task 9: Interface web `/retro` (import + vue lignes)

**Files:**
- Modify: `app/main.py`
- Create: `app/ui/templates/retro.html`
- Create: `app/ui/templates/retro_lignes.html`
- Modify: `app/ui/templates/base.html`
- Test: `tests/test_retro_web.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_retro_web.py`:

```python
from fastapi.testclient import TestClient

from app.main import creer_app, get_retro_extractor
from app.temps1.extraction_ia import MockExtractor
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne


def _retro():
    return RetroExtrait(
        type_document="retro_lgo",
        entete=RetroEntete(pharmacie_emettrice="SERALY", pharmacie_destinataire="CENON",
                           date_vente="22/09/2025", numero="N1"),
        lignes=[RetroLigne(designation="IMODIUMDUO CPR 12", code="3400937882248",
                           type_code="CIP13", qte=2, tva=10.0,
                           bl_numero="28476", bl_date="01/08/2025")])


def _client(tmp_path):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_retro_extractor] = lambda: MockExtractor(defaut=_retro())
    return TestClient(app)


def test_page_retro_200(tmp_path):
    assert _client(tmp_path).get("/retro").status_code == 200


def test_retro_ingest_un_renvoie_json(tmp_path):
    client = _client(tmp_path)
    r = client.post("/retro/ingest-un",
                    files={"fichier": ("retro.pdf", b"%PDF", "application/pdf")}).json()
    assert r["n_lignes"] == 1
    assert "n_resolu" in r and "n_rouge" in r
    assert "cout" in r and "cout_total" in r


def test_retro_lignes_200(tmp_path):
    client = _client(tmp_path)
    client.post("/retro/ingest-un",
                files={"fichier": ("retro.pdf", b"%PDF", "application/pdf")})
    r = client.get("/retro-lignes")
    assert r.status_code == 200
    assert "3400937882248" in r.text
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_retro_web.py -v`
Expected: FAIL (`get_retro_extractor` / routes absentes).

- [ ] **Step 3: Modifier `app/main.py`**

Ajouter en haut, après l'import existant de `traiter_facture` :

```python
from app.temps2.schemas import RetroExtrait
from app.temps2.traitement_retro import traiter_retro
```

Ajouter, après la fonction `get_extractor` (hors de `creer_app`) :

```python
def get_retro_extractor():
    cfg = charger_config()
    return ClaudeExtractor(cfg.get("anthropic_api_key", ""),
                           prompt_path="prompts/extraction_retro.txt",
                           output_format=RetroExtrait)
```

À l'intérieur de `creer_app`, après la définition de `_cout_total`, ajouter les helpers et routes rétro :

```python
    def _nombre_retro():
        return conn().execute("SELECT COUNT(*) n FROM retro_documents").fetchone()["n"]

    def _cout_total_retro():
        v = conn().execute(
            "SELECT COALESCE(SUM(cout_estime), 0) c FROM retro_documents").fetchone()["c"]
        return round(v, 4)

    def _ingerer_retro_un(fichier, extractor):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(fichier.file.read())
            chemin = tmp.name
        try:
            pdf = lire_pdf(chemin)
            pdf.nom = fichier.filename or pdf.nom
            res = traiter_retro(conn(), pdf, extractor, app.state.config)
            out = {"n_lignes": res.n_lignes, "n_resolu": res.n_resolu,
                   "n_rouge": res.n_rouge, "cout": round(res.cout, 5)}
        except Exception as e:
            out = {"n_lignes": 0, "n_resolu": 0, "n_rouge": 0, "cout": 0.0,
                   "erreur": f"extraction impossible : {e}"}
        finally:
            Path(chemin).unlink(missing_ok=True)
        out.update({"fichier": fichier.filename,
                    "n_total": _nombre_retro(), "cout_total": _cout_total_retro()})
        return out

    @app.get("/retro", response_class=HTMLResponse)
    def retro(request: Request):
        return TEMPLATES.TemplateResponse(
            request, "retro.html",
            {"n_total": _nombre_retro(), "cout_total": _cout_total_retro()})

    @app.post("/retro/ingest-un")
    def retro_ingest_un(fichier: UploadFile, extractor=Depends(get_retro_extractor)):
        return _ingerer_retro_un(fichier, extractor)

    @app.get("/retro-lignes", response_class=HTMLResponse)
    def retro_lignes(request: Request):
        rows = conn().execute(
            "SELECT d.numero, l.bl_numero, l.bl_date, l.designation, l.code, l.qte, "
            "l.tva, l.prix_net, l.statut_ecart "
            "FROM retro_lignes l JOIN retro_documents d ON d.id = l.retro_id "
            "ORDER BY l.id").fetchall()
        return TEMPLATES.TemplateResponse(request, "retro_lignes.html", {"rows": rows})
```

- [ ] **Step 4: Ajouter le lien de nav dans `app/ui/templates/base.html`**

Remplacer la ligne du `<nav>` :

```html
    <a href="/">Import</a><a href="/referentiel">Référentiel</a><a href="/factures">Factures</a>
```

par :

```html
    <a href="/">Import labo</a><a href="/referentiel">Référentiel</a><a href="/factures">Factures</a><a href="/retro">Rétrocession</a><a href="/retro-lignes">Lignes rétro</a>
```

- [ ] **Step 5: Créer `app/ui/templates/retro.html`**

```html
{% extends "base.html" %}
{% block contenu %}
<h1>Import factures LGO (rétrocession)</h1>

<p>Déjà en base : <strong id="n-base">{{ n_total }}</strong> factures LGO ·
   Coût cumulé : $<strong id="cout-base">{{ "%.4f"|format(cout_total or 0) }}</strong></p>

<form id="form-retro" action="/retro/ingest-un" method="post" enctype="multipart/form-data">
  <input id="input-fichiers" type="file" name="fichier" accept="application/pdf" multiple required>
  <button id="btn-retro" type="submit">Ingérer</button>
</form>

<div id="progress" style="display:none; margin-top:1rem;">
  <p>Progression : <span id="compteur">0 / 0</span></p>
  <div class="barre-fond"><div id="barre" class="barre-jauge"></div></div>
  <p id="recap"></p>
  <table>
    <tr><th>Fichier</th><th>Lignes</th><th>Résolues</th><th>Rouges</th><th>Coût $</th></tr>
    <tbody id="liste"></tbody>
  </table>
</div>

<script>
(function () {
  const form = document.getElementById("form-retro");
  const input = document.getElementById("input-fichiers");
  const td = (txt, cls) => {
    const c = document.createElement("td");
    c.textContent = txt; if (cls) c.className = cls; return c;
  };

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const files = Array.from(input.files);
    if (!files.length) return;
    const N = files.length;
    const compteur = document.getElementById("compteur");
    const barre = document.getElementById("barre");
    const liste = document.getElementById("liste");
    let coutLot = 0, resolu = 0, rouge = 0;

    document.getElementById("progress").style.display = "block";
    liste.innerHTML = "";
    document.getElementById("btn-retro").disabled = true;
    compteur.textContent = "0 / " + N;
    barre.style.width = "0%";

    for (let i = 0; i < N; i++) {
      const fd = new FormData();
      fd.append("fichier", files[i]);
      let r;
      try {
        const resp = await fetch("/retro/ingest-un", { method: "POST", body: fd });
        r = await resp.json();
      } catch (err) {
        r = { fichier: files[i].name, n_lignes: 0, n_resolu: 0, n_rouge: 0, cout: 0 };
      }
      coutLot += (r.cout || 0); resolu += (r.n_resolu || 0); rouge += (r.n_rouge || 0);
      if (r.n_total != null) document.getElementById("n-base").textContent = r.n_total;
      if (r.cout_total != null)
        document.getElementById("cout-base").textContent = Number(r.cout_total).toFixed(4);

      const tr = document.createElement("tr");
      tr.appendChild(td(r.fichier || files[i].name));
      tr.appendChild(td(String(r.n_lignes || 0)));
      tr.appendChild(td(String(r.n_resolu || 0), "ingeree"));
      tr.appendChild(td(String(r.n_rouge || 0), "en_revue"));
      tr.appendChild(td((r.cout || 0).toFixed(5)));
      liste.appendChild(tr);

      compteur.textContent = (i + 1) + " / " + N;
      barre.style.width = Math.round((i + 1) / N * 100) + "%";
      document.getElementById("recap").textContent =
        "Résolues " + resolu + " · Rouges " + rouge +
        " · Coût du lot : $" + coutLot.toFixed(4);
    }
    document.getElementById("btn-retro").disabled = false;
  });
})();
</script>
{% endblock %}
```

- [ ] **Step 6: Créer `app/ui/templates/retro_lignes.html`**

```html
{% extends "base.html" %}
{% block contenu %}
<h1>Lignes de rétrocession</h1>
<table>
  <tr><th>Facture</th><th>BL</th><th>Date BL</th><th>Désignation</th><th>Code</th>
      <th>Qté</th><th>TVA</th><th>PA net</th><th>Statut</th></tr>
  {% for r in rows %}
    <tr><td>{{ r["numero"] }}</td><td>{{ r["bl_numero"] }}</td><td>{{ r["bl_date"] }}</td>
        <td>{{ r["designation"] }}</td><td>{{ r["code"] }}</td><td>{{ r["qte"] }}</td>
        <td>{{ r["tva"] }}</td><td>{{ r["prix_net"] }}</td>
        <td class="{{ 'ingeree' if r['statut_ecart'] == 'resolu' else 'en_revue' }}">{{ r["statut_ecart"] }}</td></tr>
  {% endfor %}
</table>
{% endblock %}
```

- [ ] **Step 7: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_retro_web.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Lancer toute la suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tous les unitaires verts ; intégration deselected.

- [ ] **Step 9: Commit**

```bash
git add app/main.py app/ui/templates/retro.html app/ui/templates/retro_lignes.html app/ui/templates/base.html tests/test_retro_web.py
git commit -m "feat(temps2): interface web /retro (import LGO compteur+coût) + vue lignes"
```

---

### Task 10: Vérification finale + validation réelle

**Files:** aucun (vérification).

- [ ] **Step 1: Suite complète**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tous les unitaires verts ; `test_extraction_lgo_reelle` deselected.

- [ ] **Step 2: Démarrer l'app et vérifier les pages**

Run: `.venv/Scripts/python -m uvicorn app.main:app --reload`
Ouvrir `http://127.0.0.1:8000/retro` et `…/retro-lignes` — les pages répondent.

- [ ] **Step 3: Validation réelle (avec l'utilisateur)**

- Vérifier que `data/samples/factures_lgo/retroCenon310825Offic.pdf` est présent.
- Lancer l'intégration : `.venv/Scripts/python -m pytest -m integration -v` et inspecter
  l'extraction (en-tête émettrice/destinataire, BL/dates, TVA ≠ remise).
- Déposer le LGO via `/retro` et vérifier le récap (résolues/rouges) + `/retro-lignes`.
  Note : tant que les factures labo correspondantes ne sont pas ingérées, la majorité des
  lignes seront `rouge` (codes absents du référentiel) — comportement attendu.

---

## Self-Review (couverture du spec)

- §3 modules → Tasks 1-9. ✅
- §4 modèle de données (retro_documents, retro_lignes, correspondance_codes) → Task 1. ✅
- §5 extraction prompt B + schéma → Tasks 3, 7. ✅
- §6 matching passes 1-2 → Tasks 4, 5. ✅
- §7 calcul prix ≤ date BL + normalisation → Tasks 2, 6. ✅
- §8 orchestration → Task 8. ✅
- §9 interface web (compteur + coût) → Task 9. ✅
- §10 tests (unitaires + intégration marquée) → chaque task + Task 7. ✅
- §11 gestion d'erreurs (rouge si pas de prix / code absent / date illisible) → Tasks 6, 8. ✅
- §13 critères d'acceptation → couverts par les tests des Tasks 2-9 + validation Task 10.

Cohérence des types : `RetroExtrait` / `RetroLigne` / `RetroEntete` (Task 3) ; `normaliser_date`
(Task 2) ; `resoudre_via_correspondance` (Task 4) ; `resoudre_code` → `(code_resolu, passe)`
(Task 5) ; `prix_a_date` → dict|None (Task 6) ; `traiter_retro` → `ResultatRetro` (Task 8) ;
`ClaudeExtractor(output_format=...)` (Task 7) ; `get_retro_extractor` (Task 9).
