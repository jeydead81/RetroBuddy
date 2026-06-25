# RetroBuddy — Temps 1 (Référentiel prix) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformer un lot de factures laboratoires (PDF) en un référentiel prix historisé dans SQLite, en signalant (jamais en masquant) tout cas douteux.

**Architecture:** Cœur Python pur testable unitairement (db, checksum, filtres, garde-fous, référentiel, pipeline) piloté par une interface `Extractor` mockable ; enveloppe web FastAPI minimale. Extraction par Claude Sonnet 4.6 en lecture PDF native + sorties structurées Pydantic, avec escalade Opus 4.8 sur les factures dont les totaux ne réconcilient pas.

**Tech Stack:** Python 3.13, SQLite (stdlib `sqlite3`), `anthropic`, `pydantic` v2, `pyyaml`, `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `pytest`.

**Spec de référence :** `docs/superpowers/specs/2026-06-25-retrobuddy-temps1-referentiel-design.md`.

---

## Conventions

- Tous les chemins sont relatifs à la racine du projet `C:\Users\pharma01\Desktop\RetroBuddy`.
- Commandes lancées depuis la racine, environnement virtuel activé.
- Les tests unitaires ne font **aucun** appel réseau. L'unique test d'intégration (Task 12) est marqué `integration` et désactivé par défaut.

---

### Task 1: Scaffold du projet, dépendances, config, git

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `config.example.yaml`
- Create: `app/__init__.py`, `app/codes/__init__.py`, `app/temps1/__init__.py`, `tests/__init__.py`
- Create: `app/config.py`
- Create: `tests/test_config.py`
- Create: `README.md`

- [ ] **Step 1: Créer l'environnement virtuel et le fichier de dépendances**

Create `requirements.txt`:

```
anthropic>=0.69
pydantic>=2.7
pyyaml>=6.0
fastapi>=0.115
uvicorn>=0.30
jinja2>=3.1
python-multipart>=0.0.9
pytest>=8.0
```

Run:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -r requirements.txt
```

Expected: installation sans erreur. (Note PowerShell : activer avec `.venv\Scripts\Activate.ps1` ; sinon préfixer les commandes par `.venv/Scripts/python`.)

- [ ] **Step 2: Créer `.gitignore`**

Create `.gitignore`:

```
.venv/
__pycache__/
*.pyc
config.local.yaml
data/*.db
data/samples/
.pytest_cache/
```

- [ ] **Step 3: Créer `pyproject.toml` (config pytest)**

Create `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
markers = [
    "integration: tests qui appellent la vraie API Anthropic (désactivés par défaut)",
]
addopts = "-m 'not integration'"
```

- [ ] **Step 4: Créer les packages et la config exemple**

Create empty files: `app/__init__.py`, `app/codes/__init__.py`, `app/temps1/__init__.py`, `tests/__init__.py`.

Create `config.example.yaml`:

```yaml
# Copier en config.local.yaml (gitignored) et renseigner la clé.
anthropic_api_key: "sk-ant-xxxxx"
model_defaut: "claude-sonnet-4-6"
model_escalade: "claude-opus-4-8"
seuil_reconciliation_pct: 1.0
```

- [ ] **Step 5: Écrire le test de `charger_config`**

Create `tests/test_config.py`:

```python
from app.config import charger_config


def test_defauts_quand_fichier_absent(tmp_path):
    cfg = charger_config(tmp_path / "absent.yaml")
    assert cfg["model_defaut"] == "claude-sonnet-4-6"
    assert cfg["model_escalade"] == "claude-opus-4-8"
    assert cfg["seuil_reconciliation_pct"] == 1.0


def test_override_depuis_yaml(tmp_path):
    p = tmp_path / "config.local.yaml"
    p.write_text("seuil_reconciliation_pct: 2.5\nanthropic_api_key: cle\n", encoding="utf-8")
    cfg = charger_config(p)
    assert cfg["seuil_reconciliation_pct"] == 2.5
    assert cfg["anthropic_api_key"] == "cle"
    assert cfg["model_defaut"] == "claude-sonnet-4-6"  # défaut conservé
```

- [ ] **Step 6: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.config'`).

- [ ] **Step 7: Implémenter `app/config.py`**

Create `app/config.py`:

```python
from pathlib import Path

import yaml

DEFAUTS = {
    "model_defaut": "claude-sonnet-4-6",
    "model_escalade": "claude-opus-4-8",
    "seuil_reconciliation_pct": 1.0,
}


def charger_config(chemin="config.local.yaml"):
    cfg = dict(DEFAUTS)
    p = Path(chemin)
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        cfg.update({k: v for k, v in data.items() if v is not None})
    return cfg
```

- [ ] **Step 8: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 9: Créer le README minimal**

Create `README.md`:

```markdown
# RetroBuddy

Automatisation des factures de rétrocession inter-pharmacies. Voir
`CADRAGE_RETROCESSION.md` pour le cadrage global.

## Temps 1 — Référentiel prix

1. `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt`
2. Copier `config.example.yaml` en `config.local.yaml` et renseigner la clé API.
3. Lancer les tests : `.venv/Scripts/python -m pytest`
4. Lancer l'app : `.venv/Scripts/python -m uvicorn app.main:app --reload`
```

- [ ] **Step 10: Initialiser git et committer**

```bash
git init
git add .gitignore pyproject.toml requirements.txt config.example.yaml README.md app tests
git commit -m "chore: scaffold projet RetroBuddy + config Temps 1"
```

---

### Task 2: Schéma SQLite (`db.py`)

**Files:**
- Create: `app/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_db.py`:

```python
from app.db import get_connection, init_db


def _tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r["name"] for r in rows}


def test_init_db_cree_les_tables(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    noms = _tables(conn)
    assert {"factures", "lignes_facture", "referentiel_prix", "abreviations_labo"} <= noms


def test_init_db_idempotent(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    init_db(conn)  # ne doit pas lever
    assert "referentiel_prix" in _tables(conn)
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_db.py -v`
Expected: FAIL (`No module named 'app.db'`).

- [ ] **Step 3: Implémenter `app/db.py`**

Create `app/db.py`:

```python
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS factures (
  id INTEGER PRIMARY KEY,
  fichier TEXT,
  labo TEXT,
  numero_facture TEXT,
  date_facture TEXT,
  type_document TEXT,
  total_affiche REAL,
  total_calcule REAL,
  statut TEXT,
  motif TEXT,
  modele_extraction TEXT,
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
  checksum_ok INTEGER,
  valide INTEGER
);

CREATE TABLE IF NOT EXISTS referentiel_prix (
  code TEXT, date_facture TEXT,
  prix_brut REAL, remise_pct REAL, prix_net REAL,
  designation TEXT, facture_id INTEGER,
  PRIMARY KEY (code, date_facture)
);

CREATE TABLE IF NOT EXISTS abreviations_labo (
  abrev TEXT PRIMARY KEY, complet TEXT
);
"""


def get_connection(chemin="data/retrocession.db"):
    chemin = str(chemin)
    if chemin != ":memory:":
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_db.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: schéma SQLite Temps 1 (db.py)"
```

---

### Task 3: Validation des codes (`codes/checksum.py`)

**Files:**
- Create: `app/codes/checksum.py`
- Test: `tests/test_checksum.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_checksum.py`:

```python
from app.codes.checksum import cip13_valide, ean13_valide, type_de_code


def test_cip13_valide():
    assert cip13_valide("3400930000007") is True


def test_cip13_mauvaise_cle():
    assert cip13_valide("3400930000000") is False


def test_cip13_sans_prefixe_34009():
    # EAN13 valide mais pas un CIP (mauvais préfixe)
    assert cip13_valide("4006381333931") is False


def test_ean13_valide():
    assert ean13_valide("4006381333931") is True


def test_type_de_code():
    assert type_de_code("3400930000007") == "CIP13"
    assert type_de_code("4006381333931") == "EAN13"
    assert type_de_code("20007519") == "interne"   # code interne court (AbbVie)
    assert type_de_code("107621") == "interne"      # code interne court (Fresenius)
    assert type_de_code("3400930000000") == "inconnu"  # 13 chiffres, clé KO
    assert type_de_code(None) == "inconnu"
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_checksum.py -v`
Expected: FAIL (`No module named 'app.codes.checksum'`).

- [ ] **Step 3: Implémenter `app/codes/checksum.py`**

Create `app/codes/checksum.py`:

```python
def _cle_gtin13(douze_chiffres: str) -> int:
    total = 0
    for i, ch in enumerate(douze_chiffres):
        n = int(ch)
        total += n if i % 2 == 0 else n * 3
    return (10 - (total % 10)) % 10


def _gtin13_valide(code) -> bool:
    if not code or len(str(code)) != 13 or not str(code).isdigit():
        return False
    code = str(code)
    return _cle_gtin13(code[:12]) == int(code[12])


def ean13_valide(code) -> bool:
    return _gtin13_valide(code)


def cip13_valide(code) -> bool:
    return _gtin13_valide(code) and str(code).startswith("34009")


def type_de_code(code) -> str:
    if not code:
        return "inconnu"
    c = str(code).strip()
    if not c.isdigit():
        return "interne"
    if len(c) != 13:
        return "interne"   # codes internes courts
    if cip13_valide(c):
        return "CIP13"
    if ean13_valide(c):
        return "EAN13"
    return "inconnu"        # 13 chiffres mais clé KO → suspect
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_checksum.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/codes/checksum.py tests/test_checksum.py
git commit -m "feat: validation codes CIP13/EAN13 (checksum GTIN-13)"
```

---

### Task 4: Schémas d'extraction (`temps1/schemas.py`)

**Files:**
- Create: `app/temps1/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_schemas.py`:

```python
from app.temps1.schemas import FactureExtraite


def test_parse_facture_minimale():
    data = {
        "type_document": "facture_marchandise",
        "entete": {"labo": "URGO", "numero_facture": "F1", "date_facture": "2026-01-10",
                   "total_ht_affiche": 10.0},
        "lignes": [
            {"code": "3400930000007", "type_code": "CIP13", "code_interne": None,
             "designation": "PRODUIT A", "qte": 2, "qte_gratuite": 0,
             "prix_brut": 6.0, "remise_pct": 10.0, "remises_detail": [],
             "prix_net": 5.0, "montant_ht": 10.0, "tva": 2.1}
        ],
    }
    f = FactureExtraite.model_validate(data)
    assert f.type_document == "facture_marchandise"
    assert f.entete.labo == "URGO"
    assert len(f.lignes) == 1
    assert f.lignes[0].prix_net == 5.0
    assert f.lignes[0].qte_gratuite == 0
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_schemas.py -v`
Expected: FAIL (`No module named 'app.temps1.schemas'`).

- [ ] **Step 3: Implémenter `app/temps1/schemas.py`**

Create `app/temps1/schemas.py`:

```python
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
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_schemas.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add app/temps1/schemas.py tests/test_schemas.py
git commit -m "feat: schémas Pydantic d'extraction facture"
```

---

### Task 5: Filtres lignes valides (`temps1/filtres.py`)

**Files:**
- Create: `app/temps1/filtres.py`
- Test: `tests/test_filtres.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_filtres.py`:

```python
from app.temps1.filtres import ligne_valide
from app.temps1.schemas import LigneFacture


def _ligne(**kw):
    base = dict(code="3400930000007", designation="X", prix_brut=6.0,
                remise_pct=10.0, prix_net=5.0, montant_ht=10.0)
    base.update(kw)
    return LigneFacture(**base)


def test_ligne_normale_retenue():
    assert ligne_valide(_ligne()) is True


def test_ug_net_zero_exclue():
    assert ligne_valide(_ligne(prix_net=0.0)) is False


def test_remise_100_exclue():
    assert ligne_valide(_ligne(remise_pct=100.0)) is False


def test_sans_code_exclue():
    assert ligne_valide(_ligne(code=None)) is False


def test_prix_brut_zero_exclu():
    assert ligne_valide(_ligne(prix_brut=0.0)) is False


def test_piege_1ug_dans_le_nom_reste_valide():
    # "+1UG" est un nom commercial, pas une unité gratuite : la ligne reste valide
    assert ligne_valide(_ligne(designation="FORCAPIL ANTI-CHUTE 2MOIS + 1UG")) is True
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_filtres.py -v`
Expected: FAIL (`No module named 'app.temps1.filtres'`).

- [ ] **Step 3: Implémenter `app/temps1/filtres.py`**

Create `app/temps1/filtres.py`:

```python
from app.temps1.schemas import LigneFacture


def ligne_valide(ligne: LigneFacture) -> bool:
    """Règles §3.2 : prix brut > 0, remise < 100 %, net > 0, code rattaché."""
    if ligne.code is None or not str(ligne.code).strip():
        return False
    if ligne.prix_brut is None or ligne.prix_brut <= 0:
        return False
    if ligne.remise_pct is not None and ligne.remise_pct >= 100:
        return False
    if ligne.prix_net is None or ligne.prix_net <= 0:
        return False
    return True
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_filtres.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps1/filtres.py tests/test_filtres.py
git commit -m "feat: filtres lignes valides (§3.2)"
```

---

### Task 6: Garde-fous (`temps1/garde_fous.py`)

**Files:**
- Create: `app/temps1/garde_fous.py`
- Test: `tests/test_garde_fous.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_garde_fous.py`:

```python
from app.temps1.garde_fous import checksum_ok, reconcilier_totaux
from app.temps1.schemas import LigneFacture


def _ligne(code, montant):
    return LigneFacture(code=code, designation="X", prix_brut=6.0, remise_pct=10.0,
                        prix_net=5.0, montant_ht=montant)


def test_checksum_ok_vrai_code():
    assert checksum_ok(_ligne("3400930000007", 10.0)) is True


def test_checksum_ok_code_invalide():
    assert checksum_ok(_ligne("3400930000000", 10.0)) is False


def test_reconciliation_dans_tolerance():
    lignes = [_ligne("3400930000007", 10.0), _ligne("4006381333931", 5.0)]
    ok, total = reconcilier_totaux(lignes, total_affiche=15.0, seuil_pct=1.0)
    assert ok is True
    assert total == 15.0


def test_reconciliation_hors_tolerance():
    lignes = [_ligne("3400930000007", 10.0)]
    ok, total = reconcilier_totaux(lignes, total_affiche=20.0, seuil_pct=1.0)
    assert ok is False
    assert total == 10.0


def test_reconciliation_total_absent():
    lignes = [_ligne("3400930000007", 10.0)]
    ok, total = reconcilier_totaux(lignes, total_affiche=None, seuil_pct=1.0)
    assert ok is False
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_garde_fous.py -v`
Expected: FAIL (`No module named 'app.temps1.garde_fous'`).

- [ ] **Step 3: Implémenter `app/temps1/garde_fous.py`**

Create `app/temps1/garde_fous.py`:

```python
from app.codes.checksum import type_de_code
from app.temps1.schemas import LigneFacture


def checksum_ok(ligne: LigneFacture) -> bool:
    """Vrai si le code porté par la ligne est un CIP13 ou EAN13 valide."""
    return type_de_code(ligne.code) in ("CIP13", "EAN13")


def reconcilier_totaux(lignes, total_affiche, seuil_pct=1.0, seuil_abs=0.02):
    """Compare la somme des montants HT extraits au total HT affiché.

    Retourne (ok, total_calcule). La somme couvre TOUTES les lignes extraites
    (validation de l'extraction), indépendamment des filtres §3.2.
    """
    total_calcule = sum(l.montant_ht for l in lignes if l.montant_ht is not None)
    if total_affiche is None:
        return (False, total_calcule)
    ecart = abs(total_calcule - total_affiche)
    tolere = max(seuil_abs, abs(total_affiche) * seuil_pct / 100)
    return (ecart <= tolere, total_calcule)
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_garde_fous.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps1/garde_fous.py tests/test_garde_fous.py
git commit -m "feat: garde-fous checksum + réconciliation totaux (§5)"
```

---

### Task 7: Classification (`temps1/classifier.py`)

**Files:**
- Create: `app/temps1/classifier.py`
- Test: `tests/test_classifier.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_classifier.py`:

```python
from app.temps1.classifier import decision
from app.temps1.schemas import EnteteFacture, FactureExtraite


def _facture(type_document):
    return FactureExtraite(type_document=type_document, entete=EnteteFacture(), lignes=[])


def test_facture_marchandise_a_traiter():
    dec, motif = decision(_facture("facture_marchandise"))
    assert dec == "traiter"
    assert motif is None


def test_avoir_ignore():
    dec, motif = decision(_facture("avoir"))
    assert dec == "ignorer"
    assert "avoir" in motif.lower()


def test_abonnement_ignore():
    dec, _ = decision(_facture("abonnement_service"))
    assert dec == "ignorer"


def test_releve_ignore():
    dec, _ = decision(_facture("releve"))
    assert dec == "ignorer"


def test_type_inconnu_ignore():
    dec, motif = decision(_facture("grossiste"))
    assert dec == "ignorer"
    assert "grossiste" in motif
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_classifier.py -v`
Expected: FAIL (`No module named 'app.temps1.classifier'`).

- [ ] **Step 3: Implémenter `app/temps1/classifier.py`**

Create `app/temps1/classifier.py`:

```python
from app.temps1.schemas import FactureExtraite

TYPES_A_TRAITER = {"facture_marchandise"}

MOTIFS = {
    "avoir": "avoir (exclu du référentiel)",
    "abonnement_service": "abonnement / prestation",
    "releve": "relevé d'échéances",
    "autre": "document non traité en V1",
}


def decision(facture: FactureExtraite):
    """Retourne ('traiter', None) ou ('ignorer', motif)."""
    t = facture.type_document
    if t in TYPES_A_TRAITER:
        return ("traiter", None)
    return ("ignorer", MOTIFS.get(t, f"type non traité: {t}"))
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_classifier.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps1/classifier.py tests/test_classifier.py
git commit -m "feat: classification documents (§4)"
```

---

### Task 8: Lecture PDF (`temps1/pdf_reader.py`)

**Files:**
- Create: `app/temps1/pdf_reader.py`
- Test: `tests/test_pdf_reader.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_pdf_reader.py`:

```python
import base64

from app.temps1.pdf_reader import lire_pdf


def test_lire_pdf_encode_base64(tmp_path):
    contenu = b"%PDF-1.4 fake bytes"
    f = tmp_path / "facture.pdf"
    f.write_bytes(contenu)

    doc = lire_pdf(f)

    assert doc.nom == "facture.pdf"
    assert doc.taille_octets == len(contenu)
    assert base64.standard_b64decode(doc.base64) == contenu
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_pdf_reader.py -v`
Expected: FAIL (`No module named 'app.temps1.pdf_reader'`).

- [ ] **Step 3: Implémenter `app/temps1/pdf_reader.py`**

Create `app/temps1/pdf_reader.py`:

```python
import base64
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PdfDocument:
    nom: str
    base64: str
    taille_octets: int


def lire_pdf(chemin) -> PdfDocument:
    p = Path(chemin)
    octets = p.read_bytes()
    return PdfDocument(
        nom=p.name,
        base64=base64.standard_b64encode(octets).decode("ascii"),
        taille_octets=len(octets),
    )
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_pdf_reader.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add app/temps1/pdf_reader.py tests/test_pdf_reader.py
git commit -m "feat: lecture PDF → bloc document base64"
```

---

### Task 9: Interface Extractor + MockExtractor (`temps1/extraction_ia.py`)

**Files:**
- Create: `app/temps1/extraction_ia.py`
- Test: `tests/test_extraction_ia.py`

> Le `ClaudeExtractor` réel (appel API) est ajouté au même fichier en Task 12. Ici on
> ne pose que l'interface et le mock, testables sans réseau.

- [ ] **Step 1: Écrire le test**

Create `tests/test_extraction_ia.py`:

```python
from app.temps1.extraction_ia import MockExtractor
from app.temps1.pdf_reader import PdfDocument
from app.temps1.schemas import EnteteFacture, FactureExtraite


def _pdf():
    return PdfDocument(nom="f.pdf", base64="", taille_octets=0)


def _facture(t):
    return FactureExtraite(type_document=t, entete=EnteteFacture(), lignes=[])


def test_mock_retourne_le_defaut():
    f = _facture("facture_marchandise")
    ex = MockExtractor(defaut=f)
    assert ex.extraire(_pdf(), "claude-sonnet-4-6") is f


def test_mock_retourne_par_modele_et_trace_les_appels():
    fs = _facture("facture_marchandise")
    fo = _facture("avoir")
    ex = MockExtractor(par_modele={"claude-sonnet-4-6": fs, "claude-opus-4-8": fo})
    assert ex.extraire(_pdf(), "claude-sonnet-4-6") is fs
    assert ex.extraire(_pdf(), "claude-opus-4-8") is fo
    assert ex.appels == [("f.pdf", "claude-sonnet-4-6"), ("f.pdf", "claude-opus-4-8")]
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_extraction_ia.py -v`
Expected: FAIL (`No module named 'app.temps1.extraction_ia'`).

- [ ] **Step 3: Implémenter `app/temps1/extraction_ia.py`**

Create `app/temps1/extraction_ia.py`:

```python
from typing import Protocol

from app.temps1.pdf_reader import PdfDocument
from app.temps1.schemas import FactureExtraite


class Extractor(Protocol):
    def extraire(self, pdf: PdfDocument, model: str) -> FactureExtraite: ...


class MockExtractor:
    """Extracteur de test : renvoie une facture par modèle, ou un défaut."""

    def __init__(self, par_modele=None, defaut=None):
        self.par_modele = par_modele or {}
        self.defaut = defaut
        self.appels = []

    def extraire(self, pdf: PdfDocument, model: str) -> FactureExtraite:
        self.appels.append((pdf.nom, model))
        if model in self.par_modele:
            return self.par_modele[model]
        if self.defaut is not None:
            return self.defaut
        raise KeyError(f"Aucune facture mock pour le modèle {model}")
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_extraction_ia.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps1/extraction_ia.py tests/test_extraction_ia.py
git commit -m "feat: interface Extractor + MockExtractor"
```

---

### Task 10: Écriture du référentiel (`temps1/referentiel.py`)

**Files:**
- Create: `app/temps1/referentiel.py`
- Test: `tests/test_referentiel.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_referentiel.py`:

```python
from app.db import get_connection, init_db
from app.temps1.referentiel import enregistrer_lignes_referentiel
from app.temps1.schemas import LigneFacture


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ligne(code, net):
    return LigneFacture(code=code, designation="X", prix_brut=6.0, remise_pct=10.0,
                        prix_net=net, montant_ht=net)


def test_historisation_deux_dates(tmp_path):
    conn = _conn(tmp_path)
    enregistrer_lignes_referentiel(conn, 1, "2026-01-10", [_ligne("3400930000007", 5.0)])
    enregistrer_lignes_referentiel(conn, 2, "2026-02-10", [_ligne("3400930000007", 4.5)])
    rows = conn.execute(
        "SELECT date_facture, prix_net FROM referentiel_prix WHERE code=? ORDER BY date_facture",
        ("3400930000007",),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["prix_net"] == 5.0
    assert rows[1]["prix_net"] == 4.5


def test_idempotence_meme_code_meme_date(tmp_path):
    conn = _conn(tmp_path)
    enregistrer_lignes_referentiel(conn, 1, "2026-01-10", [_ligne("3400930000007", 5.0)])
    enregistrer_lignes_referentiel(conn, 9, "2026-01-10", [_ligne("3400930000007", 4.0)])
    rows = conn.execute(
        "SELECT prix_net, facture_id FROM referentiel_prix WHERE code=?",
        ("3400930000007",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["prix_net"] == 4.0      # remplacé par la dernière ingestion
    assert rows[0]["facture_id"] == 9
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_referentiel.py -v`
Expected: FAIL (`No module named 'app.temps1.referentiel'`).

- [ ] **Step 3: Implémenter `app/temps1/referentiel.py`**

Create `app/temps1/referentiel.py`:

```python
def enregistrer_lignes_referentiel(conn, facture_id, date_facture, lignes):
    """Upsert des lignes retenues dans le référentiel historisé (code, date_facture)."""
    for l in lignes:
        conn.execute(
            """
            INSERT INTO referentiel_prix
              (code, date_facture, prix_brut, remise_pct, prix_net, designation, facture_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, date_facture) DO UPDATE SET
              prix_brut=excluded.prix_brut,
              remise_pct=excluded.remise_pct,
              prix_net=excluded.prix_net,
              designation=excluded.designation,
              facture_id=excluded.facture_id
            """,
            (l.code, date_facture, l.prix_brut, l.remise_pct, l.prix_net,
             l.designation, facture_id),
        )
    conn.commit()
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_referentiel.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps1/referentiel.py tests/test_referentiel.py
git commit -m "feat: écriture du référentiel prix historisé"
```

---

### Task 11: Pipeline d'orchestration (`temps1/pipeline.py`)

**Files:**
- Create: `app/temps1/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_pipeline.py`:

```python
from app.db import get_connection, init_db
from app.temps1.extraction_ia import MockExtractor
from app.temps1.pdf_reader import PdfDocument
from app.temps1.pipeline import traiter_facture
from app.temps1.schemas import EnteteFacture, FactureExtraite, LigneFacture

CFG = {"model_defaut": "claude-sonnet-4-6", "model_escalade": "claude-opus-4-8",
       "seuil_reconciliation_pct": 1.0}


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _pdf():
    return PdfDocument(nom="f.pdf", base64="", taille_octets=0)


def _facture(type_document="facture_marchandise", lignes=None, total=None):
    return FactureExtraite(
        type_document=type_document,
        entete=EnteteFacture(labo="URGO", numero_facture="F1",
                             date_facture="2026-01-10", total_ht_affiche=total),
        lignes=lignes or [],
    )


def _ligne(code="3400930000007", net=5.0, montant=10.0):
    return LigneFacture(code=code, designation="X", prix_brut=6.0, remise_pct=10.0,
                        prix_net=net, montant_ht=montant)


def test_facture_nominale_ingeree(tmp_path):
    conn = _conn(tmp_path)
    f = _facture(lignes=[_ligne(montant=10.0)], total=10.0)
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "ingeree"
    assert res.n_referentiel == 1
    n = conn.execute("SELECT COUNT(*) c FROM referentiel_prix").fetchone()["c"]
    assert n == 1


def test_avoir_ignore(tmp_path):
    conn = _conn(tmp_path)
    f = _facture(type_document="avoir")
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "ignoree"
    assert conn.execute("SELECT COUNT(*) c FROM referentiel_prix").fetchone()["c"] == 0


def test_totaux_non_reconcilies_en_revue(tmp_path):
    conn = _conn(tmp_path)
    f = _facture(lignes=[_ligne(montant=10.0)], total=99.0)
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "en_revue"
    assert conn.execute("SELECT COUNT(*) c FROM referentiel_prix").fetchone()["c"] == 0


def test_escalade_opus_recupere(tmp_path):
    conn = _conn(tmp_path)
    sonnet = _facture(lignes=[_ligne(montant=10.0)], total=99.0)   # ne réconcilie pas
    opus = _facture(lignes=[_ligne(montant=10.0)], total=10.0)     # réconcilie
    ex = MockExtractor(par_modele={"claude-sonnet-4-6": sonnet, "claude-opus-4-8": opus})
    res = traiter_facture(conn, _pdf(), ex, CFG)
    assert res.statut == "ingeree"
    assert ex.appels == [("f.pdf", "claude-sonnet-4-6"), ("f.pdf", "claude-opus-4-8")]
    fid = res.facture_id
    modele = conn.execute("SELECT modele_extraction FROM factures WHERE id=?", (fid,)).fetchone()
    assert modele["modele_extraction"] == "claude-opus-4-8"


def test_ligne_checksum_invalide_exclue_du_referentiel(tmp_path):
    conn = _conn(tmp_path)
    # code à clé invalide → ligne flaggée, hors référentiel, mais total réconcilie
    f = _facture(lignes=[_ligne(code="3400930000000", montant=10.0)], total=10.0)
    res = traiter_facture(conn, _pdf(), MockExtractor(defaut=f), CFG)
    assert res.statut == "ingeree"
    assert res.n_referentiel == 0
    ligne = conn.execute("SELECT checksum_ok, valide FROM lignes_facture").fetchone()
    assert ligne["checksum_ok"] == 0
    assert ligne["valide"] == 0
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL (`No module named 'app.temps1.pipeline'`).

- [ ] **Step 3: Implémenter `app/temps1/pipeline.py`**

Create `app/temps1/pipeline.py`:

```python
from dataclasses import dataclass

from app.temps1 import classifier, filtres, garde_fous
from app.temps1.referentiel import enregistrer_lignes_referentiel


@dataclass
class Resultat:
    statut: str               # 'ingeree' | 'ignoree' | 'en_revue'
    motif: str | None
    facture_id: int | None
    total_calcule: float | None
    n_referentiel: int


def _persister(conn, pdf, facture, statut, motif, modele, total_calcule):
    cur = conn.execute(
        """
        INSERT INTO factures
          (fichier, labo, numero_facture, date_facture, type_document,
           total_affiche, total_calcule, statut, motif, modele_extraction)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (pdf.nom, facture.entete.labo, facture.entete.numero_facture,
         facture.entete.date_facture, facture.type_document,
         facture.entete.total_ht_affiche, total_calcule, statut, motif, modele),
    )
    facture_id = cur.lastrowid
    for l in facture.lignes:
        cok = garde_fous.checksum_ok(l)
        retenue = filtres.ligne_valide(l) and cok
        conn.execute(
            """
            INSERT INTO lignes_facture
              (facture_id, code, type_code, code_interne, designation, qte, qte_gratuite,
               prix_brut, remise_pct, prix_net, montant_ht, tva, checksum_ok, valide)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (facture_id, l.code, l.type_code, l.code_interne, l.designation, l.qte,
             l.qte_gratuite, l.prix_brut, l.remise_pct, l.prix_net, l.montant_ht, l.tva,
             int(cok), int(retenue)),
        )
    conn.commit()
    return facture_id


def _lignes_retenues(facture):
    return [l for l in facture.lignes
            if filtres.ligne_valide(l) and garde_fous.checksum_ok(l)]


def traiter_facture(conn, pdf, extractor, config) -> Resultat:
    seuil = config["seuil_reconciliation_pct"]

    facture = extractor.extraire(pdf, config["model_defaut"])
    modele = config["model_defaut"]

    dec, motif = classifier.decision(facture)
    if dec == "ignorer":
        fid = _persister(conn, pdf, facture, "ignoree", motif, modele, None)
        return Resultat("ignoree", motif, fid, None, 0)

    ok, total = garde_fous.reconcilier_totaux(
        facture.lignes, facture.entete.total_ht_affiche, seuil)

    if not ok:
        # Escalade : une seule re-extraction en Opus
        modele = config["model_escalade"]
        facture = extractor.extraire(pdf, modele)
        dec, motif = classifier.decision(facture)
        if dec == "ignorer":
            fid = _persister(conn, pdf, facture, "ignoree", motif, modele, None)
            return Resultat("ignoree", motif, fid, None, 0)
        ok, total = garde_fous.reconcilier_totaux(
            facture.lignes, facture.entete.total_ht_affiche, seuil)
        if not ok:
            m = "totaux non réconciliés (Sonnet + Opus)"
            fid = _persister(conn, pdf, facture, "en_revue", m, modele, total)
            return Resultat("en_revue", m, fid, total, 0)

    fid = _persister(conn, pdf, facture, "ingeree", None, modele, total)
    retenues = _lignes_retenues(facture)
    enregistrer_lignes_referentiel(conn, fid, facture.entete.date_facture, retenues)
    return Resultat("ingeree", None, fid, total, len(retenues))
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_pipeline.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lancer toute la suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: PASS (tous les tests unitaires verts).

- [ ] **Step 6: Commit**

```bash
git add app/temps1/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline d'orchestration Temps 1 (classif → garde-fous → escalade → référentiel)"
```

---

### Task 12: ClaudeExtractor réel + prompt A + test d'intégration

**Files:**
- Modify: `app/temps1/extraction_ia.py`
- Create: `prompts/extraction_facture.txt`
- Test: `tests/test_extraction_integration.py`

- [ ] **Step 1: Écrire le prompt A**

Create `prompts/extraction_facture.txt`:

```
Tu es un extracteur de factures de laboratoires pharmaceutiques. Tu reçois une
facture en PDF et tu produis un JSON STRICT conforme au schéma imposé.

RÈGLES IMPÉRATIVES :
1. CLASSIFIER d'abord le document via "type_document" :
   - "facture_marchandise" : lignes produit, total HT positif.
   - "avoir" : présence de AVOIR, "Avoir net de taxe", montants négatifs.
   - "abonnement_service" : abonnement logiciel, prestation, autocollants, mobilier.
   - "releve" : relevé d'échéances.
   - "autre" : grossiste ou document non identifié.
2. Pour chaque ligne produit, renseigner le PRIX NET tel qu'AFFICHÉ sur la facture.
   Ne JAMAIS recalculer le net à partir d'une seule remise (cas multi-remises).
3. CODE : "code" doit être le vrai code à 13 chiffres (CIP13 préfixe 34009, ou EAN13).
   Se fier au CONTENU du code (clé de contrôle), pas à son intitulé. Si la facture
   porte un code interne court (non 13 chiffres), le mettre dans "code_interne" et
   laisser "code" à null si aucun code 13 n'est présent.
4. NE PAS extraire les récapitulatifs tarifaires (texte libre sans codes ni quantités
   livrées) : renseigner une liste de lignes vide pour ces pages.
5. PIÈGE UG : "UG" dans une désignation (ex. "... + 1UG") est un NOM COMMERCIAL, pas
   une unité gratuite. Ne pas confondre avec "qte_gratuite".
6. Les unités gratuites réelles (colonne "gratuit"/"UG", ou ligne séparée remise 100 %)
   vont dans "qte_gratuite" ; ne pas les compter comme des lignes de prix.

Réponds UNIQUEMENT avec le JSON conforme au schéma fourni.
```

- [ ] **Step 2: Ajouter `ClaudeExtractor` à `app/temps1/extraction_ia.py`**

Add to the top imports of `app/temps1/extraction_ia.py`:

```python
from pathlib import Path

import anthropic
```

Append to `app/temps1/extraction_ia.py`:

```python
class ExtractionError(RuntimeError):
    pass


class ClaudeExtractor:
    """Extracteur réel : envoie le PDF à Claude (lecture native) avec sortie structurée."""

    def __init__(self, api_key: str, prompt_path="prompts/extraction_facture.txt"):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._prompt = Path(prompt_path).read_text(encoding="utf-8")

    def extraire(self, pdf: PdfDocument, model: str) -> FactureExtraite:
        resp = self._client.messages.parse(
            model=model,
            max_tokens=16000,
            system=[{"type": "text", "text": self._prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document",
                     "source": {"type": "base64", "media_type": "application/pdf",
                                "data": pdf.base64}},
                    {"type": "text", "text": "Extrais cette facture selon le schéma."},
                ],
            }],
            output_format=FactureExtraite,
        )
        if resp.stop_reason == "refusal":
            raise ExtractionError("extraction refusée par le modèle")
        if resp.parsed_output is None:
            raise ExtractionError("extraction non conforme au schéma")
        return resp.parsed_output
```

- [ ] **Step 3: Vérifier que les tests unitaires existants passent toujours**

Run: `.venv/Scripts/python -m pytest tests/test_extraction_ia.py -v`
Expected: PASS (le mock n'est pas affecté ; l'import de `anthropic` doit être installé).

- [ ] **Step 4: Écrire le test d'intégration (marqué, désactivé par défaut)**

Create `tests/test_extraction_integration.py`:

```python
"""Test d'intégration : appelle la vraie API. Lancer avec :
    .venv/Scripts/python -m pytest -m integration
Nécessite config.local.yaml (clé) et au moins un PDF dans data/samples/factures_labo/.
"""
from pathlib import Path

import pytest

from app.config import charger_config
from app.temps1.extraction_ia import ClaudeExtractor
from app.temps1.pdf_reader import lire_pdf

SAMPLES = Path("data/samples/factures_labo")


@pytest.mark.integration
def test_extraction_reelle_premier_pdf():
    cfg = charger_config()
    if not cfg.get("anthropic_api_key"):
        pytest.skip("clé API absente de config.local.yaml")
    pdfs = sorted(SAMPLES.glob("*.pdf")) if SAMPLES.exists() else []
    if not pdfs:
        pytest.skip("aucun PDF dans data/samples/factures_labo/")

    ex = ClaudeExtractor(cfg["anthropic_api_key"])
    facture = ex.extraire(lire_pdf(pdfs[0]), cfg["model_defaut"])

    assert facture.type_document in {
        "facture_marchandise", "avoir", "abonnement_service", "releve", "autre"}
```

- [ ] **Step 5: Vérifier que le test d'intégration est bien ignoré par défaut**

Run: `.venv/Scripts/python -m pytest -v`
Expected: les tests unitaires passent ; `test_extraction_integration` est **deselected** (grâce à `addopts = -m 'not integration'`).

- [ ] **Step 6: Commit**

```bash
git add app/temps1/extraction_ia.py prompts/extraction_facture.txt tests/test_extraction_integration.py
git commit -m "feat: ClaudeExtractor réel (PDF natif + sortie structurée) + prompt A"
```

> **Validation manuelle (hors plan automatisé), à faire avec l'utilisateur :** une fois
> les vrais PDF déposés dans `data/samples/factures_labo/` et la clé renseignée, lancer
> `.venv/Scripts/python -m pytest -m integration -v` et inspecter le résultat.

---

### Task 13: Interface web FastAPI (`app/main.py` + templates)

**Files:**
- Create: `app/main.py`
- Create: `app/ui/templates/base.html`
- Create: `app/ui/templates/accueil.html`
- Create: `app/ui/templates/referentiel.html`
- Create: `app/ui/templates/factures.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: Écrire le test web (TestClient + override de l'extracteur)**

Create `tests/test_web.py`:

```python
from fastapi.testclient import TestClient

from app.main import creer_app, get_extractor
from app.temps1.extraction_ia import MockExtractor
from app.temps1.schemas import EnteteFacture, FactureExtraite, LigneFacture


def _facture():
    return FactureExtraite(
        type_document="facture_marchandise",
        entete=EnteteFacture(labo="URGO", numero_facture="F1",
                             date_facture="2026-01-10", total_ht_affiche=10.0),
        lignes=[LigneFacture(code="3400930000007", designation="X", prix_brut=6.0,
                             remise_pct=10.0, prix_net=5.0, montant_ht=10.0)],
    )


def _client(tmp_path):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_extractor] = lambda: MockExtractor(defaut=_facture())
    return TestClient(app)


def test_accueil_200(tmp_path):
    assert _client(tmp_path).get("/").status_code == 200


def test_factures_vide_200(tmp_path):
    r = _client(tmp_path).get("/factures")
    assert r.status_code == 200


def test_ingest_ajoute_au_referentiel(tmp_path):
    client = _client(tmp_path)
    files = [("fichiers", ("f.pdf", b"%PDF-1.4 fake", "application/pdf"))]
    r = client.post("/ingest", files=files)
    assert r.status_code == 200
    assert "ingérée" in r.text or "ingeree" in r.text.lower()
    ref = client.get("/referentiel")
    assert "3400930000007" in ref.text
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_web.py -v`
Expected: FAIL (`No module named 'app.main'` ou `cannot import name 'creer_app'`).

- [ ] **Step 3: Implémenter `app/main.py`**

Create `app/main.py`:

```python
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import charger_config
from app.db import get_connection, init_db
from app.temps1.extraction_ia import ClaudeExtractor
from app.temps1.pdf_reader import lire_pdf
from app.temps1.pipeline import traiter_facture

TEMPLATES = Jinja2Templates(directory="app/ui/templates")


def get_extractor():
    cfg = charger_config()
    return ClaudeExtractor(cfg.get("anthropic_api_key", ""))


def creer_app(db_path="data/retrocession.db") -> FastAPI:
    app = FastAPI(title="RetroBuddy — Temps 1")
    app.state.db_path = db_path
    app.state.config = charger_config()

    init_db(get_connection(db_path))

    def conn():
        return get_connection(app.state.db_path)

    @app.get("/", response_class=HTMLResponse)
    def accueil(request: Request):
        return TEMPLATES.TemplateResponse(request, "accueil.html", {})

    @app.post("/ingest", response_class=HTMLResponse)
    def ingest(request: Request, fichiers: list[UploadFile],
               extractor=Depends(get_extractor)):
        c = conn()
        recap = {"ingeree": 0, "ignoree": 0, "en_revue": 0}
        details = []
        for f in fichiers:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(f.file.read())
                chemin = tmp.name
            pdf = lire_pdf(chemin)
            pdf.nom = f.filename or pdf.nom
            res = traiter_facture(c, pdf, extractor, app.state.config)
            recap[res.statut] = recap.get(res.statut, 0) + 1
            details.append((f.filename, res.statut, res.motif))
            Path(chemin).unlink(missing_ok=True)
        return TEMPLATES.TemplateResponse(
            request, "accueil.html", {"recap": recap, "details": details})

    @app.get("/referentiel", response_class=HTMLResponse)
    def referentiel(request: Request):
        rows = conn().execute(
            "SELECT code, date_facture, designation, prix_brut, remise_pct, prix_net "
            "FROM referentiel_prix ORDER BY code, date_facture").fetchall()
        return TEMPLATES.TemplateResponse(request, "referentiel.html", {"rows": rows})

    @app.get("/factures", response_class=HTMLResponse)
    def factures(request: Request):
        rows = conn().execute(
            "SELECT id, fichier, labo, type_document, statut, motif, total_affiche, "
            "total_calcule, modele_extraction FROM factures ORDER BY id DESC").fetchall()
        return TEMPLATES.TemplateResponse(request, "factures.html", {"rows": rows})

    @app.get("/export-base")
    def export_base():
        return FileResponse(app.state.db_path, filename="retrocession.db")

    @app.post("/import-base")
    def import_base(fichier: UploadFile):
        Path(app.state.db_path).write_bytes(fichier.file.read())
        return RedirectResponse("/factures", status_code=303)

    return app


app = creer_app()
```

- [ ] **Step 4: Créer les templates**

Create `app/ui/templates/base.html`:

```html
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>RetroBuddy — Temps 1</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; }
    nav a { margin-right: 1rem; }
    table { border-collapse: collapse; margin-top: 1rem; }
    th, td { border: 1px solid #ccc; padding: .3rem .6rem; font-size: .9rem; }
    .ingeree { color: #137333; } .ignoree { color: #777; } .en_revue { color: #b00; }
  </style>
</head>
<body>
  <nav>
    <a href="/">Import</a><a href="/referentiel">Référentiel</a><a href="/factures">Factures</a>
  </nav>
  {% block contenu %}{% endblock %}
</body>
</html>
```

Create `app/ui/templates/accueil.html`:

```html
{% extends "base.html" %}
{% block contenu %}
<h1>Import factures labo</h1>
<form action="/ingest" method="post" enctype="multipart/form-data">
  <input type="file" name="fichiers" accept="application/pdf" multiple required>
  <button type="submit">Ingérer</button>
</form>
{% if recap %}
  <h2>Résultat</h2>
  <ul>
    <li class="ingeree">Ingérées : {{ recap.get("ingeree", 0) }}</li>
    <li class="ignoree">Ignorées : {{ recap.get("ignoree", 0) }}</li>
    <li class="en_revue">En revue : {{ recap.get("en_revue", 0) }}</li>
  </ul>
  <table>
    <tr><th>Fichier</th><th>Statut</th><th>Motif</th></tr>
    {% for nom, statut, motif in details %}
      <tr><td>{{ nom }}</td><td class="{{ statut }}">{{ statut }}</td><td>{{ motif or "" }}</td></tr>
    {% endfor %}
  </table>
{% endif %}
{% endblock %}
```

Create `app/ui/templates/referentiel.html`:

```html
{% extends "base.html" %}
{% block contenu %}
<h1>Référentiel prix</h1>
<table>
  <tr><th>Code</th><th>Date</th><th>Désignation</th><th>PA brut</th><th>Remise %</th><th>PA net</th></tr>
  {% for r in rows %}
    <tr><td>{{ r["code"] }}</td><td>{{ r["date_facture"] }}</td><td>{{ r["designation"] }}</td>
        <td>{{ r["prix_brut"] }}</td><td>{{ r["remise_pct"] }}</td><td>{{ r["prix_net"] }}</td></tr>
  {% endfor %}
</table>
{% endblock %}
```

Create `app/ui/templates/factures.html`:

```html
{% extends "base.html" %}
{% block contenu %}
<h1>Factures</h1>
<p>
  <a href="/export-base">Exporter la base</a>
</p>
<table>
  <tr><th>#</th><th>Fichier</th><th>Labo</th><th>Type</th><th>Statut</th><th>Motif</th>
      <th>Total affiché</th><th>Total calculé</th><th>Modèle</th></tr>
  {% for r in rows %}
    <tr><td>{{ r["id"] }}</td><td>{{ r["fichier"] }}</td><td>{{ r["labo"] }}</td>
        <td>{{ r["type_document"] }}</td><td class="{{ r['statut'] }}">{{ r["statut"] }}</td>
        <td>{{ r["motif"] or "" }}</td><td>{{ r["total_affiche"] }}</td>
        <td>{{ r["total_calcule"] }}</td><td>{{ r["modele_extraction"] }}</td></tr>
  {% endfor %}
</table>
{% endblock %}
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_web.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Lancer toute la suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: tous les tests unitaires verts ; intégration deselected.

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/ui/templates
git commit -m "feat: interface web FastAPI (import, référentiel, factures, export base)"
```

---

### Task 14: Vérification finale et démarrage manuel

**Files:** aucun (vérification).

- [ ] **Step 1: Lancer la suite complète**

Run: `.venv/Scripts/python -m pytest -v`
Expected: tous les tests unitaires verts ; `test_extraction_integration` deselected.

- [ ] **Step 2: Démarrer l'app et vérifier les pages**

Run: `.venv/Scripts/python -m uvicorn app.main:app --reload`
Then: ouvrir `http://127.0.0.1:8000/`, `…/referentiel`, `…/factures` — les trois pages répondent.

- [ ] **Step 3: Validation réelle (avec l'utilisateur)**

- Renseigner `config.local.yaml` (clé API).
- Déposer de vrais PDF labo dans `data/samples/factures_labo/`.
- Lancer le test d'intégration : `.venv/Scripts/python -m pytest -m integration -v`.
- Déposer les PDF via l'UI `/` et vérifier le récap + le référentiel + les factures en revue.

- [ ] **Step 4: Commit éventuel de la documentation**

```bash
git add -A
git commit -m "docs: notes de vérification Temps 1" || echo "rien à committer"
```

---

## Self-Review (couverture du spec)

- §2.1 modules → Tasks 2–13 (un module par task ou groupe). ✅
- §2.2 flux nominal → Task 11 (`pipeline.traiter_facture`). ✅
- §2.3 escalade modèle → Task 11 (`test_escalade_opus_recupere`). ✅
- §3 modèle de données → Task 2. ✅
- §4 extraction (prompt A + schéma + sortie structurée) → Tasks 4, 12. ✅
- §5.1 classification → Task 7 ; §5.2 filtres → Task 5 ; §5.3 garde-fous → Task 6 ;
  §5.4 checksum → Task 3. ✅
- §6 interface web → Task 13. ✅
- §7 config/secrets → Task 1 (`.gitignore`, `config.example.yaml`, `config.py`). ✅
- §8 tests (mock + intégration marquée) → Tasks 9, 11, 12. ✅
- §9 gestion d'erreurs → Task 12 (`ExtractionError`), Task 11 (en_revue). ✅
- §12 critères d'acceptation → couverts par les tests des Tasks 5–13 + validation manuelle Task 14.

Cohérence des types : `FactureExtraite` / `LigneFacture` / `EnteteFacture` (Task 4) utilisés
partout ; `traiter_facture` / `Resultat` (Task 11) ; `Extractor` / `MockExtractor` /
`ClaudeExtractor` (Tasks 9, 12) ; `PdfDocument` / `lire_pdf` (Task 8) ; `charger_config`
(Task 1) ; `enregistrer_lignes_referentiel` (Task 10) ; `get_connection` / `init_db` (Task 2).
