# RetroBuddy — Temps 3 (Résolution + matching désignation + ingestion en tâche de fond) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L'étape humaine de résolution : un matching par désignation (passes 3-4) génère des candidats orange, un tableau type Excel (`/resolution`) permet de compléter/valider, et l'ingestion tourne côté serveur pour survivre à la navigation entre onglets.

**Architecture:** Réutilise l'infra Temps 1-2 (SQLite, `ClaudeExtractor`, couche FastAPI). Matching désignation déterministe (normalisation + `difflib`, sans API). Tableau de résolution en vanilla JS avec sauvegarde par ligne. Ingestion via un registre de jobs en mémoire + threads + polling, avec reprise via `localStorage`.

**Tech Stack:** Python 3.13, SQLite, FastAPI, jinja2, `difflib`/`unicodedata`/`threading` (stdlib), pytest.

**Spec de référence :** `docs/superpowers/specs/2026-06-26-retrobuddy-temps3-resolution-design.md`.

---

## Conventions

- Chemins relatifs à `C:\Users\pharma01\Desktop\RetroBuddy`. Python/pytest via `.venv/Scripts/python`.
- Tests unitaires : aucun appel réseau (MockExtractor + matching déterministe).
- Les tables `retro_lignes`, `referentiel_prix`, `abreviations_labo` existent déjà.

---

### Task 1: Normalisation des désignations (`temps2/normalisation_designation.py`)

**Files:**
- Create: `app/temps2/normalisation_designation.py`
- Test: `tests/test_normalisation_designation.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_normalisation_designation.py`:

```python
from app.db import get_connection, init_db
from app.temps2.normalisation_designation import (
    charger_abreviations, dosages_concordants, extraire_dosage,
    normaliser_designation, score_designation)


def test_normalise_majuscule_accents_ponctuation():
    assert normaliser_designation("Doliprane 1000mg, cpr.") == "DOLIPRANE 1000MG CPR"


def test_normalise_chaine_vide():
    assert normaliser_designation(None) == ""


def test_expansion_abreviation():
    assert normaliser_designation("LRP cicaplast", {"LRP": "LA ROCHE POSAY"}) == \
        "LA ROCHE POSAY CICAPLAST"


def test_extraire_dosage():
    assert extraire_dosage("CICAPLAST B5 200ML") == {"B5", "200ML"}


def test_dosages_concordants():
    assert dosages_concordants("DOLIPRANE 1000MG", "Doliprane 1000 mg") is True
    assert dosages_concordants("DOLIPRANE 1000MG", "DOLIPRANE 500MG") is False


def test_score_identique_vaut_1():
    assert score_designation("DOLIPRANE 1000MG", "doliprane 1000 mg") == 1.0


def test_score_proche_eleve():
    assert score_designation("ANTHELIOS 50 AGE CORRECT", "ANTHELIOS 50 AGE CORRECT PARFUM") >= 0.8


def test_score_eloigne_bas():
    assert score_designation("DOLIPRANE", "EFFERALGAN") < 0.5


def test_charger_abreviations(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    conn.execute("INSERT INTO abreviations_labo (abrev, complet) VALUES (?, ?)",
                 ("LRP", "LA ROCHE POSAY"))
    conn.commit()
    assert charger_abreviations(conn) == {"LRP": "LA ROCHE POSAY"}
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_normalisation_designation.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/temps2/normalisation_designation.py`**

```python
import difflib
import re
import unicodedata


def charger_abreviations(conn):
    return {r["abrev"]: r["complet"]
            for r in conn.execute("SELECT abrev, complet FROM abreviations_labo")}


def normaliser_designation(s, abreviations=None):
    if not s:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))   # enlève accents
    t = t.upper()
    t = re.sub(r"[^A-Z0-9]+", " ", t)                            # ponctuation -> espace
    t = re.sub(r"\s+", " ", t).strip()
    if abreviations:
        t = " ".join(abreviations.get(m, m) for m in t.split())
        t = re.sub(r"[^A-Z0-9 ]+", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
    return t


def extraire_dosage(s):
    """Tokens porteurs d'un chiffre (dosage/contenance : 1000MG, 200ML, B5, 350G…)."""
    return {t for t in normaliser_designation(s).split() if any(c.isdigit() for c in t)}


def dosages_concordants(a, b):
    return extraire_dosage(a) == extraire_dosage(b)


def _tokens_tries(s):
    return " ".join(sorted(normaliser_designation(s).split()))


def score_designation(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, _tokens_tries(a), _tokens_tries(b)).ratio()
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_normalisation_designation.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps2/normalisation_designation.py tests/test_normalisation_designation.py
git commit -m "feat(temps3): normalisation designations + score (deterministe)"
```

---

### Task 2: Matching par désignation (`matching.py` étendu)

**Files:**
- Modify: `app/temps2/matching.py`
- Test: `tests/test_matching_designation.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_matching_designation.py`:

```python
from app.db import get_connection, init_db
from app.temps2.matching import resoudre_par_designation


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code, designation):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_net, designation) "
        "VALUES (?, ?, ?, ?)",
        (code, "2025-08-01", 5.0, designation))
    conn.commit()


def test_candidat_par_designation_proche(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930156421", "REXORUBIA GLE 350G")
    code, desig, score = resoudre_par_designation(conn, "REXORUBIA GLE 350 G", 0.80)
    assert code == "3400930156421"
    assert desig == "REXORUBIA GLE 350G"
    assert score >= 0.95


def test_aucun_candidat_sous_le_seuil(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400930156421", "REXORUBIA GLE 350G")
    code, desig, score = resoudre_par_designation(conn, "DOLIPRANE 1000MG", 0.80)
    assert code is None
    assert desig is None


def test_meilleur_candidat(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "A", "ANTHELIOS 50 AGE CORRECT AVEC PARFUM")
    _ref(conn, "B", "DOLIPRANE 1000MG")
    code, desig, score = resoudre_par_designation(conn, "ANTHELIOS 50 AGE CORRECT", 0.70)
    assert code == "A"
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_matching_designation.py -v`
Expected: FAIL (fonction absente).

- [ ] **Step 3: Étendre `app/temps2/matching.py`**

Ajouter cet import en haut du fichier (après l'import existant de `resoudre_via_correspondance`) :

```python
from app.temps2.normalisation_designation import normaliser_designation, score_designation
```

Puis APPENDER à la fin du fichier :

```python
def resoudre_par_designation(conn, designation, seuil_bas, abreviations=None):
    """Cherche dans le référentiel la meilleure désignation proche (passes 3-4).

    Retourne (code, designation_referentiel, score) si score >= seuil_bas,
    sinon (None, None, 0.0).
    """
    cible = normaliser_designation(designation, abreviations)
    if not cible:
        return (None, None, 0.0)
    meilleur = (None, None, 0.0)
    vu = set()
    for r in conn.execute(
            "SELECT DISTINCT code, designation FROM referentiel_prix WHERE code IS NOT NULL"):
        cle = (r["code"], r["designation"])
        if cle in vu:
            continue
        vu.add(cle)
        s = score_designation(cible, normaliser_designation(r["designation"], abreviations))
        if s > meilleur[2]:
            meilleur = (r["code"], r["designation"], s)
    if meilleur[2] >= seuil_bas:
        return meilleur
    return (None, None, 0.0)
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_matching_designation.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps2/matching.py tests/test_matching_designation.py
git commit -m "feat(temps3): resoudre_par_designation (passes 3-4)"
```

---

### Task 3: Seuils de matching dans la config (`config.py`)

**Files:**
- Modify: `app/config.py`
- Modify: `config.example.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Écrire le test (ajout à `tests/test_config.py`)**

Ajouter à la fin de `tests/test_config.py` :

```python
def test_defauts_seuils_matching(tmp_path):
    cfg = charger_config(tmp_path / "absent.yaml")
    assert cfg["seuil_match_bas"] == 0.80
    assert cfg["seuil_match_auto"] == 0.95
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_config.py::test_defauts_seuils_matching -v`
Expected: FAIL (clés absentes).

- [ ] **Step 3: Étendre `DEFAUTS` dans `app/config.py`**

Remplacer le dict `DEFAUTS` par :

```python
DEFAUTS = {
    "model_defaut": "claude-sonnet-4-6",
    "model_escalade": "claude-opus-4-8",
    "seuil_reconciliation_pct": 1.0,
    "seuil_match_bas": 0.80,
    "seuil_match_auto": 0.95,
}
```

- [ ] **Step 4: Mettre à jour `config.example.yaml`**

Ajouter ces deux lignes à la fin de `config.example.yaml` :

```yaml
seuil_match_bas: 0.80
seuil_match_auto: 0.95
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: PASS (tous).

- [ ] **Step 6: Commit**

```bash
git add app/config.py config.example.yaml tests/test_config.py
git commit -m "feat(temps3): seuils de matching designation configurables"
```

---

### Task 4: Intégration passes 3-4 + auto-validation (`traitement_retro.py`)

**Files:**
- Modify: `app/temps2/traitement_retro.py`
- Test: `tests/test_traitement_retro_designation.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_traitement_retro_designation.py`:

```python
from app.db import get_connection, init_db
from app.temps1.extraction_ia import MockExtractor
from app.temps1.pdf_reader import PdfDocument
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne
from app.temps2.traitement_retro import traiter_retro

CFG = {"model_defaut": "claude-sonnet-4-6", "model_escalade": "claude-opus-4-8",
       "seuil_match_bas": 0.80, "seuil_match_auto": 0.95}


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ref(conn, code, date_facture, prix_net, designation):
    conn.execute(
        "INSERT INTO referentiel_prix (code, date_facture, prix_brut, remise_pct, prix_net, designation) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (code, date_facture, prix_net + 1, 10.0, prix_net, designation))
    conn.commit()


def _pdf():
    return PdfDocument(nom="retro.pdf", base64="", taille_octets=0)


def _retro(lignes):
    return RetroExtrait(type_document="retro_lgo",
                        entete=RetroEntete(pharmacie_emettrice="A", pharmacie_destinataire="B"),
                        lignes=lignes)


def _ligne(code, designation, bl_date="10/08/2025"):
    return RetroLigne(designation=designation, code=code, type_code="CIP13", qte=1,
                      tva=10.0, bl_numero="BL1", bl_date=bl_date)


def test_orange_par_designation_autovalide(tmp_path):
    conn = _conn(tmp_path)
    # référentiel : même désignation, code différent de celui (absent) de la ligne LGO
    _ref(conn, "3400930156421", "01/08/2025", 4.5, "REXORUBIA GLE 350G")
    retro = _retro([_ligne("9999999999999", "REXORUBIA GLE 350 G")])  # code LGO introuvable
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_orange == 1
    r = conn.execute("SELECT statut_ecart, code_resolu, prix_net, passe_match, "
                     "score_match, valide_utilisateur FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "orange"
    assert r["code_resolu"] == "3400930156421"
    assert r["prix_net"] == 4.5
    assert r["passe_match"] in (3, 4)
    assert r["score_match"] >= 0.95
    assert r["valide_utilisateur"] == 1     # score eleve + dosage concordant


def test_orange_a_confirmer_si_dosage_discordant(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "C1", "01/08/2025", 4.5, "DOLIPRANE 500MG")
    retro = _retro([_ligne("9999999999999", "DOLIPRANE 1000MG")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    # dosage discordant -> pas de match au-dessus du seuil bas, donc rouge
    assert res.n_rouge == 1


def test_priorite_code_sur_designation(tmp_path):
    conn = _conn(tmp_path)
    _ref(conn, "3400937882248", "01/08/2025", 2.0, "IMODIUMDUO CPR 12")
    retro = _retro([_ligne("3400937882248", "AUTRE DESIGNATION")])
    res = traiter_retro(conn, _pdf(), MockExtractor(defaut=retro), CFG)
    assert res.n_resolu == 1     # passe 1 (code) prioritaire, statut resolu (vert)
    r = conn.execute("SELECT statut_ecart, passe_match FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "resolu"
    assert r["passe_match"] == 1
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_traitement_retro_designation.py -v`
Expected: FAIL (`n_orange` / comportement absent).

- [ ] **Step 3: Réécrire `app/temps2/traitement_retro.py`**

```python
from dataclasses import dataclass

from app.temps2 import calcul_prix, matching
from app.temps2.normalisation_designation import charger_abreviations, dosages_concordants


@dataclass
class ResultatRetro:
    retro_id: int
    n_lignes: int
    n_resolu: int
    n_rouge: int
    cout: float = 0.0
    n_orange: int = 0


def traiter_retro(conn, pdf, extractor, config) -> ResultatRetro:
    retro = extractor.extraire(pdf, config["model_defaut"])
    cout = getattr(extractor, "dernier_cout", 0.0)
    seuil_bas = config.get("seuil_match_bas", 0.80)
    seuil_auto = config.get("seuil_match_auto", 0.95)
    abrev = charger_abreviations(conn)

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

    n_resolu = n_rouge = n_orange = 0
    for l in retro.lignes:
        code_resolu, passe = matching.resoudre_code(conn, l.code)   # passes 1-2
        score = None
        cand_desig = None
        if code_resolu is None:                                     # passes 3-4
            cand_code, cand_desig, score = matching.resoudre_par_designation(
                conn, l.designation, seuil_bas, abrev)
            if cand_code is not None:
                code_resolu = cand_code
                passe = 3 if score >= 1.0 else 4

        prix = calcul_prix.prix_a_date(conn, code_resolu, l.bl_date) if code_resolu else None
        valide = 0
        if prix is not None:
            pb, rp, pn = prix["prix_brut"], prix["remise_pct"], prix["prix_net"]
            if passe in (1, 2):
                statut, n_resolu = "resolu", n_resolu + 1
            else:
                statut, n_orange = "orange", n_orange + 1
                if (score is not None and score >= seuil_auto
                        and dosages_concordants(l.designation, cand_desig)):
                    valide = 1
        else:
            statut, n_rouge = "rouge", n_rouge + 1
            pb = rp = pn = None

        conn.execute(
            """
            INSERT INTO retro_lignes
              (retro_id, designation, code, type_code, qte, tva, bl_numero, bl_date,
               code_resolu, prix_brut, remise_pct, prix_net, passe_match, score_match,
               statut_ecart, valide_utilisateur)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (retro_id, l.designation, l.code, l.type_code, l.qte, l.tva, l.bl_numero,
             l.bl_date, code_resolu, pb, rp, pn, passe, score, statut, valide),
        )
    conn.commit()
    return ResultatRetro(retro_id, len(retro.lignes), n_resolu, n_rouge, cout, n_orange)
```

- [ ] **Step 4: Lancer les tests rétro (nouveaux + anciens)**

Run: `.venv/Scripts/python -m pytest tests/test_traitement_retro_designation.py tests/test_traitement_retro.py -v`
Expected: PASS (les anciens tests Temps 2 restent verts ; les nouveaux passent).

- [ ] **Step 5: Commit**

```bash
git add app/temps2/traitement_retro.py tests/test_traitement_retro_designation.py
git commit -m "feat(temps3): integration passes 3-4 + auto-validation orange"
```

---

### Task 5: Re-rapprochement à la demande (`temps3/rematch.py`)

**Files:**
- Create: `app/temps3/__init__.py`
- Create: `app/temps3/rematch.py`
- Test: `tests/test_rematch.py`

- [ ] **Step 1: Créer le package**

Créer le fichier vide `app/temps3/__init__.py`.

- [ ] **Step 2: Écrire le test**

Create `tests/test_rematch.py`:

```python
from app.db import get_connection, init_db
from app.temps3.rematch import rematcher

CFG = {"seuil_match_bas": 0.80, "seuil_match_auto": 0.95}


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _retro_doc(conn):
    cur = conn.execute("INSERT INTO retro_documents (fichier) VALUES ('r.pdf')")
    return cur.lastrowid


def _ligne_rouge(conn, retro_id, code, designation, bl_date="10/08/2025"):
    conn.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, qte, tva, bl_numero, bl_date, "
        "statut_ecart, valide_utilisateur, saisie_manuelle) "
        "VALUES (?, ?, ?, 1, 10.0, 'BL1', ?, 'rouge', 0, 0)",
        (retro_id, designation, code, bl_date))
    conn.commit()


def test_rematch_passe_rouge_en_resolu_apres_ajout_referentiel(tmp_path):
    conn = _conn(tmp_path)
    rid = _retro_doc(conn)
    _ligne_rouge(conn, rid, "3400937882248", "IMODIUMDUO CPR 12")
    # au départ : aucune correspondance -> reste rouge
    assert rematcher(conn, CFG)["resolu"] == 0
    # on ajoute la facture labo au référentiel
    conn.execute("INSERT INTO referentiel_prix (code, date_facture, prix_brut, remise_pct, "
                 "prix_net, designation) VALUES ('3400937882248', '01/08/2025', 3.0, 10.0, 2.7, "
                 "'IMODIUMDUO CPR 12')")
    conn.commit()
    compteurs = rematcher(conn, CFG)
    assert compteurs["resolu"] == 1
    r = conn.execute("SELECT statut_ecart, prix_net FROM retro_lignes").fetchone()
    assert r["statut_ecart"] == "resolu"
    assert r["prix_net"] == 2.7


def test_rematch_epargne_les_lignes_saisies(tmp_path):
    conn = _conn(tmp_path)
    rid = _retro_doc(conn)
    conn.execute("INSERT INTO retro_lignes (retro_id, designation, code, qte, tva, bl_numero, "
                 "bl_date, prix_net, statut_ecart, valide_utilisateur, saisie_manuelle) "
                 "VALUES (?, 'X', '3400937882248', 1, 10.0, 'BL1', '10/08/2025', 9.9, 'rouge', 0, 1)",
                 (rid,))
    conn.execute("INSERT INTO referentiel_prix (code, date_facture, prix_net, designation) "
                 "VALUES ('3400937882248', '01/08/2025', 2.7, 'X')")
    conn.commit()
    rematcher(conn, CFG)
    # ligne saisie manuellement : non touchée
    assert conn.execute("SELECT prix_net FROM retro_lignes").fetchone()["prix_net"] == 9.9
```

- [ ] **Step 3: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_rematch.py -v`
Expected: FAIL (module absent).

- [ ] **Step 4: Implémenter `app/temps3/rematch.py`**

```python
from app.temps2 import calcul_prix, matching
from app.temps2.normalisation_designation import charger_abreviations, dosages_concordants


def rematcher(conn, config):
    """Rejoue passes 1-4 + calcul prix sur les lignes ni validées ni saisies.

    Retourne les compteurs {resolu, orange, rouge} des lignes re-traitées.
    """
    seuil_bas = config.get("seuil_match_bas", 0.80)
    seuil_auto = config.get("seuil_match_auto", 0.95)
    abrev = charger_abreviations(conn)
    compteurs = {"resolu": 0, "orange": 0, "rouge": 0}

    lignes = conn.execute(
        "SELECT id, code, designation, bl_date FROM retro_lignes "
        "WHERE valide_utilisateur = 0 AND saisie_manuelle = 0").fetchall()

    for l in lignes:
        code_resolu, passe = matching.resoudre_code(conn, l["code"])
        score, cand_desig = None, None
        if code_resolu is None:
            cand_code, cand_desig, score = matching.resoudre_par_designation(
                conn, l["designation"], seuil_bas, abrev)
            if cand_code is not None:
                code_resolu = cand_code
                passe = 3 if score >= 1.0 else 4

        prix = calcul_prix.prix_a_date(conn, code_resolu, l["bl_date"]) if code_resolu else None
        valide = 0
        if prix is not None:
            pb, rp, pn = prix["prix_brut"], prix["remise_pct"], prix["prix_net"]
            if passe in (1, 2):
                statut = "resolu"
            else:
                statut = "orange"
                if (score is not None and score >= seuil_auto
                        and dosages_concordants(l["designation"], cand_desig)):
                    valide = 1
        else:
            statut, pb, rp, pn = "rouge", None, None, None

        compteurs[statut] += 1
        conn.execute(
            "UPDATE retro_lignes SET code_resolu=?, prix_brut=?, remise_pct=?, prix_net=?, "
            "passe_match=?, score_match=?, statut_ecart=?, valide_utilisateur=? WHERE id=?",
            (code_resolu, pb, rp, pn, passe, score, statut, valide, l["id"]))
    conn.commit()
    return compteurs
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_rematch.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add app/temps3/__init__.py app/temps3/rematch.py tests/test_rematch.py
git commit -m "feat(temps3): re-rapprochement a la demande (rematch)"
```

---

### Task 6: Logique de résolution d'une ligne (`temps3/resolution.py`)

**Files:**
- Create: `app/temps3/resolution.py`
- Test: `tests/test_resolution.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_resolution.py`:

```python
from app.db import get_connection, init_db
from app.temps3.resolution import (
    accepter_orange, calcul_net, enregistrer_ligne, refuser_orange)


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _ligne(conn, **kw):
    base = dict(retro_id=1, designation="X", qte=2.0, statut_ecart="rouge",
                valide_utilisateur=0, saisie_manuelle=0)
    base.update(kw)
    cols = ", ".join(base)
    ph = ", ".join("?" for _ in base)
    cur = conn.execute(f"INSERT INTO retro_lignes ({cols}) VALUES ({ph})", tuple(base.values()))
    conn.commit()
    return cur.lastrowid


def test_calcul_net_sans_ug():
    assert calcul_net(qte=2, prix_brut=10.0, remise_pct=20.0, ug=0) == 8.0


def test_calcul_net_avec_ug():
    # (2 * 10 * 0.8) / (2 + 2) = 16 / 4 = 4.0
    assert calcul_net(qte=2, prix_brut=10.0, remise_pct=20.0, ug=2) == 4.0


def test_enregistrer_ligne_recalcule_et_valide(tmp_path):
    conn = _conn(tmp_path)
    lid = _ligne(conn)
    r = enregistrer_ligne(conn, lid, prix_brut=10.0, remise_pct=20.0, ug=0)
    assert r["prix_net"] == 8.0
    row = conn.execute("SELECT prix_net, statut_ecart, valide_utilisateur, saisie_manuelle "
                       "FROM retro_lignes WHERE id=?", (lid,)).fetchone()
    assert row["prix_net"] == 8.0
    assert row["valide_utilisateur"] == 1
    assert row["saisie_manuelle"] == 1
    assert row["statut_ecart"] == "resolu"


def test_accepter_orange(tmp_path):
    conn = _conn(tmp_path)
    lid = _ligne(conn, statut_ecart="orange", prix_net=4.5, code_resolu="C")
    accepter_orange(conn, lid)
    row = conn.execute("SELECT statut_ecart, valide_utilisateur FROM retro_lignes WHERE id=?",
                       (lid,)).fetchone()
    assert row["statut_ecart"] == "resolu"
    assert row["valide_utilisateur"] == 1


def test_refuser_orange_repasse_rouge(tmp_path):
    conn = _conn(tmp_path)
    lid = _ligne(conn, statut_ecart="orange", prix_net=4.5, code_resolu="C")
    refuser_orange(conn, lid)
    row = conn.execute("SELECT statut_ecart, valide_utilisateur, prix_net, code_resolu "
                       "FROM retro_lignes WHERE id=?", (lid,)).fetchone()
    assert row["statut_ecart"] == "rouge"
    assert row["valide_utilisateur"] == 0
    assert row["prix_net"] is None
    assert row["code_resolu"] is None
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_resolution.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/temps3/resolution.py`**

```python
def calcul_net(qte, prix_brut, remise_pct, ug=0):
    """PA net unitaire (cadrage §3.3) : qte*brut*(1-remise/100)/(qte+ug)."""
    qte = qte or 0
    ug = ug or 0
    if prix_brut is None or (qte + ug) == 0:
        return None
    remise = remise_pct or 0
    return round(qte * prix_brut * (1 - remise / 100) / (qte + ug), 4)


def _qte(conn, ligne_id):
    r = conn.execute("SELECT qte FROM retro_lignes WHERE id=?", (ligne_id,)).fetchone()
    return r["qte"] if r else 0


def enregistrer_ligne(conn, ligne_id, prix_brut=None, remise_pct=None, prix_net=None, ug=0):
    """Sauvegarde une saisie manuelle : recalcule le net (sauf si net fourni), valide la ligne."""
    qte = _qte(conn, ligne_id)
    net = prix_net if prix_net is not None else calcul_net(qte, prix_brut, remise_pct, ug)
    valide = 1 if (net is not None and net > 0) else 0
    statut = "resolu" if valide else "rouge"
    conn.execute(
        "UPDATE retro_lignes SET prix_brut=?, remise_pct=?, prix_net=?, ug=?, "
        "saisie_manuelle=1, valide_utilisateur=?, statut_ecart=? WHERE id=?",
        (prix_brut, remise_pct, net, ug, valide, statut, ligne_id))
    conn.commit()
    return {"id": ligne_id, "prix_net": net, "statut_ecart": statut, "valide_utilisateur": valide}


def accepter_orange(conn, ligne_id):
    """Confirme un candidat orange : la ligne devient résolue."""
    conn.execute(
        "UPDATE retro_lignes SET valide_utilisateur=1, statut_ecart='resolu' WHERE id=?",
        (ligne_id,))
    conn.commit()


def refuser_orange(conn, ligne_id):
    """Rejette un candidat orange : la ligne repasse rouge (à compléter à la main)."""
    conn.execute(
        "UPDATE retro_lignes SET statut_ecart='rouge', valide_utilisateur=0, code_resolu=NULL, "
        "prix_brut=NULL, remise_pct=NULL, prix_net=NULL, passe_match=NULL, score_match=NULL "
        "WHERE id=?",
        (ligne_id,))
    conn.commit()
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_resolution.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/temps3/resolution.py tests/test_resolution.py
git commit -m "feat(temps3): logique de resolution (calcul net, save, accepter, refuser)"
```

---

### Task 7: Page de résolution web (`/resolution`)

**Files:**
- Modify: `app/main.py`
- Create: `app/ui/templates/resolution.html`
- Modify: `app/ui/templates/base.html`
- Test: `tests/test_resolution_web.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_resolution_web.py`:

```python
from fastapi.testclient import TestClient

from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _ligne(client, **kw):
    # insère une ligne directement en base via une connexion de l'app
    from app.db import get_connection
    conn = get_connection(client.app.state.db_path)
    conn.execute("INSERT INTO retro_documents (id, numero) VALUES (1, 'N1')")
    base = dict(retro_id=1, designation="REXORUBIA", qte=2.0, statut_ecart="rouge",
                valide_utilisateur=0, saisie_manuelle=0)
    base.update(kw)
    cols = ", ".join(base); ph = ", ".join("?" for _ in base)
    cur = conn.execute(f"INSERT INTO retro_lignes ({cols}) VALUES ({ph})", tuple(base.values()))
    conn.commit()
    return cur.lastrowid


def test_page_resolution_200(tmp_path):
    assert _client(tmp_path).get("/resolution").status_code == 200


def test_resolution_masque_les_resolus(tmp_path):
    client = _client(tmp_path)
    _ligne(client, designation="ROUGE_VISIBLE", statut_ecart="rouge")
    _ligne(client, designation="VERT_CACHE", statut_ecart="resolu")
    html = client.get("/resolution").text
    assert "ROUGE_VISIBLE" in html
    assert "VERT_CACHE" not in html


def test_enregistrer_ligne_endpoint(tmp_path):
    client = _client(tmp_path)
    lid = _ligne(client)
    r = client.post(f"/resolution/ligne/{lid}",
                    json={"prix_brut": 10.0, "remise_pct": 20.0, "ug": 0})
    assert r.status_code == 200
    assert r.json()["prix_net"] == 8.0


def test_accepter_et_refuser(tmp_path):
    client = _client(tmp_path)
    lid = _ligne(client, statut_ecart="orange", prix_net=4.5, code_resolu="C")
    assert client.post(f"/resolution/ligne/{lid}/accepter").status_code == 200
    lid2 = _ligne(client, statut_ecart="orange", prix_net=4.5, code_resolu="C")
    assert client.post(f"/resolution/ligne/{lid2}/refuser").status_code == 200


def test_rematch_endpoint(tmp_path):
    r = _client(tmp_path).post("/resolution/rematch")
    assert r.status_code == 200
    assert "resolu" in r.json()
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_resolution_web.py -v`
Expected: FAIL (routes absentes).

- [ ] **Step 3: Modifier `app/main.py`**

(a) Ajouter ces imports après l'import de `traiter_retro` :

```python
from app.temps3 import resolution as resolution_logique
from app.temps3.rematch import rematcher
```

(b) À l'intérieur de `creer_app`, juste avant les routes favicon, ajouter :

```python
    @app.get("/resolution", response_class=HTMLResponse)
    def resolution(request: Request):
        rows = conn().execute(
            "SELECT l.id, l.designation, l.code, l.code_resolu, l.qte, l.tva, "
            "l.bl_numero, l.bl_date, l.prix_brut, l.remise_pct, l.prix_net, l.ug, "
            "l.score_match, l.statut_ecart, l.valide_utilisateur "
            "FROM retro_lignes l "
            "WHERE l.statut_ecart IN ('rouge', 'orange') ORDER BY l.id").fetchall()
        n_rouge = sum(1 for r in rows if r["statut_ecart"] == "rouge")
        n_orange_a_confirmer = sum(
            1 for r in rows if r["statut_ecart"] == "orange" and not r["valide_utilisateur"])
        n_auto = sum(
            1 for r in rows if r["statut_ecart"] == "orange" and r["valide_utilisateur"])
        compteurs = {"rouge": n_rouge, "a_confirmer": n_orange_a_confirmer,
                     "auto": n_auto, "total": len(rows)}
        return TEMPLATES.TemplateResponse(
            request, "resolution.html", {"rows": rows, "compteurs": compteurs})

    @app.post("/resolution/ligne/{ligne_id}")
    def resolution_enregistrer(ligne_id: int, payload: dict):
        return resolution_logique.enregistrer_ligne(
            conn(), ligne_id,
            prix_brut=payload.get("prix_brut"), remise_pct=payload.get("remise_pct"),
            prix_net=payload.get("prix_net"), ug=payload.get("ug", 0))

    @app.post("/resolution/ligne/{ligne_id}/accepter")
    def resolution_accepter(ligne_id: int):
        resolution_logique.accepter_orange(conn(), ligne_id)
        return {"ok": True}

    @app.post("/resolution/ligne/{ligne_id}/refuser")
    def resolution_refuser(ligne_id: int):
        resolution_logique.refuser_orange(conn(), ligne_id)
        return {"ok": True}

    @app.post("/resolution/rematch")
    def resolution_rematch():
        return rematcher(conn(), app.state.config)
```

- [ ] **Step 4: Ajouter le lien nav dans `app/ui/templates/base.html`**

Dans la ligne `<nav>`, ajouter `<a href="/resolution">Résolution</a>` juste après le lien `Lignes rétro`. La ligne devient :

```html
    <a href="/">Import labo</a><a href="/referentiel">Référentiel</a><a href="/factures">Factures</a><a href="/retro">Rétrocession</a><a href="/retro-lignes">Lignes rétro</a><a href="/resolution">Résolution</a>
```

- [ ] **Step 5: Créer `app/ui/templates/resolution.html`**

```html
{% extends "base.html" %}
{% block contenu %}
<h1>Résolution des écarts</h1>
<p>
  <strong class="en_revue">À compléter (rouge) : {{ compteurs.rouge }}</strong> ·
  À confirmer (orange) : {{ compteurs.a_confirmer }} ·
  Auto-validées : {{ compteurs.auto }} ·
  <button onclick="rematch()">Re-rapprocher</button>
</p>
<div class="barre-fond">
  <div class="barre-jauge" style="width: {{ (100 * compteurs.auto / compteurs.total) if compteurs.total else 0 }}%"></div>
</div>

<table id="table-resolution">
  <tr>
    <th>Désignation LGO</th><th>Code</th><th>Qté</th><th>BL</th><th>Date BL</th>
    <th>Candidat (score)</th><th>PA brut</th><th>Remise %</th><th>UG</th><th>PA net</th>
    <th>Statut</th><th>Action</th>
  </tr>
  {% for r in rows %}
  <tr data-id="{{ r['id'] }}" class="ligne {{ r['statut_ecart'] }}">
    <td>{{ r["designation"] }}</td>
    <td>{{ r["code"] }}</td>
    <td>{{ r["qte"] }}</td>
    <td>{{ r["bl_numero"] }}</td>
    <td>{{ r["bl_date"] }}</td>
    <td>{% if r["statut_ecart"] == "orange" %}{{ r["code_resolu"] }} ({{ "%.2f"|format(r["score_match"] or 0) }}){% endif %}</td>
    <td><input class="f-brut" type="number" step="0.001" value="{{ r['prix_brut'] if r['prix_brut'] is not none else '' }}"></td>
    <td><input class="f-remise" type="number" step="0.01" value="{{ r['remise_pct'] if r['remise_pct'] is not none else '' }}"></td>
    <td><input class="f-ug" type="number" step="1" value="{{ r['ug'] if r['ug'] is not none else 0 }}"></td>
    <td><input class="f-net" type="number" step="0.001" value="{{ r['prix_net'] if r['prix_net'] is not none else '' }}"></td>
    <td class="statut {{ r['statut_ecart'] }}">{{ r["statut_ecart"] }}{% if r["valide_utilisateur"] %} ✓{% endif %}</td>
    <td>
      {% if r["statut_ecart"] == "orange" %}
        <button onclick="accepter({{ r['id'] }})">Accepter</button>
        <button onclick="refuser({{ r['id'] }})">Refuser</button>
      {% else %}
        <button onclick="enregistrer({{ r['id'] }})">Enregistrer</button>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
</table>

<script>
function valeur(tr, cls) {
  const v = tr.querySelector(cls).value;
  return v === "" ? null : parseFloat(v);
}
async function enregistrer(id) {
  const tr = document.querySelector(`tr[data-id="${id}"]`);
  const payload = {
    prix_brut: valeur(tr, ".f-brut"), remise_pct: valeur(tr, ".f-remise"),
    ug: valeur(tr, ".f-ug") || 0, prix_net: valeur(tr, ".f-net")
  };
  const r = await fetch(`/resolution/ligne/${id}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const d = await r.json();
  tr.querySelector(".f-net").value = d.prix_net != null ? d.prix_net : "";
  tr.querySelector(".statut").textContent = d.statut_ecart + (d.valide_utilisateur ? " ✓" : "");
}
// recalcul du net à la volée quand brut/remise/ug changent (sans toucher si net saisi à la main)
document.querySelectorAll("#table-resolution tr[data-id]").forEach(tr => {
  ["change"].forEach(ev => tr.addEventListener(ev, e => {
    if (!e.target.matches(".f-brut, .f-remise, .f-ug")) return;
    const qte = parseFloat(tr.querySelector("td:nth-child(3)").textContent) || 0;
    const brut = valeur(tr, ".f-brut"), remise = valeur(tr, ".f-remise") || 0, ug = valeur(tr, ".f-ug") || 0;
    if (brut != null && (qte + ug) > 0)
      tr.querySelector(".f-net").value = (qte * brut * (1 - remise / 100) / (qte + ug)).toFixed(4);
  }));
});
async function accepter(id) { await fetch(`/resolution/ligne/${id}/accepter`, { method: "POST" }); location.reload(); }
async function refuser(id) { await fetch(`/resolution/ligne/${id}/refuser`, { method: "POST" }); location.reload(); }
async function rematch() { await fetch(`/resolution/rematch`, { method: "POST" }); location.reload(); }
</script>
{% endblock %}
```

- [ ] **Step 6: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_resolution_web.py -v`
Expected: PASS (5 tests).

- [ ] **Step 7: Lancer toute la suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tous les unitaires verts ; intégration deselected.

- [ ] **Step 8: Commit**

```bash
git add app/main.py app/ui/templates/resolution.html app/ui/templates/base.html tests/test_resolution_web.py
git commit -m "feat(temps3): page de resolution (tableau, compteurs, save, accepter/refuser, rematch)"
```

---

### Task 8: Registre de jobs d'ingestion (`jobs.py`)

**Files:**
- Create: `app/jobs.py`
- Test: `tests/test_jobs.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_jobs.py`:

```python
from app.jobs import RegistreJobs, lancer_job


def test_job_traite_tous_les_fichiers():
    reg = RegistreJobs()
    jid = reg.creer(2)
    appels = []

    def traiter_un(nom, chemin):
        appels.append(nom)
        return {"fichier": nom, "statut": "ok", "cout": 0.01}

    t = lancer_job(reg, jid, [("a.pdf", "/tmp/a"), ("b.pdf", "/tmp/b")], traiter_un)
    t.join(timeout=5)
    j = reg.lire(jid)
    assert j["termine"] is True
    assert j["fait"] == 2
    assert round(j["cout"], 2) == 0.02
    assert len(j["details"]) == 2
    assert appels == ["a.pdf", "b.pdf"]


def test_job_inconnu_renvoie_none():
    assert RegistreJobs().lire("zzz") is None


def test_job_continue_malgre_une_erreur():
    reg = RegistreJobs()
    jid = reg.creer(2)

    def traiter_un(nom, chemin):
        if nom == "boom.pdf":
            raise RuntimeError("boom")
        return {"fichier": nom, "statut": "ok", "cout": 0.0}

    t = lancer_job(reg, jid, [("boom.pdf", "/tmp/x"), ("ok.pdf", "/tmp/y")], traiter_un)
    t.join(timeout=5)
    j = reg.lire(jid)
    assert j["fait"] == 2
    assert j["details"][0]["statut"] == "erreur"
    assert j["details"][1]["statut"] == "ok"
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/jobs.py`**

```python
import threading
import uuid


class RegistreJobs:
    """Registre en mémoire des jobs d'ingestion (app mono-processus local)."""

    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def creer(self, total):
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {"total": total, "fait": 0, "cout": 0.0,
                                  "details": [], "termine": False}
        return job_id

    def ajouter(self, job_id, resultat):
        with self._lock:
            j = self._jobs.get(job_id)
            if j is not None:
                j["fait"] += 1
                j["cout"] = round(j["cout"] + float(resultat.get("cout", 0.0)), 5)
                j["details"].append(resultat)

    def terminer(self, job_id):
        with self._lock:
            j = self._jobs.get(job_id)
            if j is not None:
                j["termine"] = True

    def lire(self, job_id):
        with self._lock:
            j = self._jobs.get(job_id)
            return {"total": j["total"], "fait": j["fait"], "cout": j["cout"],
                    "details": list(j["details"]), "termine": j["termine"]} if j else None


def lancer_job(registre, job_id, fichiers, traiter_un):
    """Démarre un thread qui traite chaque (nom, chemin) via traiter_un(nom, chemin) -> dict.

    Un fichier qui échoue n'interrompt pas le lot. Retourne le thread (pour join en test).
    """
    def _run():
        for nom, chemin in fichiers:
            try:
                r = traiter_un(nom, chemin)
            except Exception as e:
                r = {"fichier": nom, "statut": "erreur", "motif": str(e), "cout": 0.0}
            registre.ajouter(job_id, r)
        registre.terminer(job_id)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/jobs.py tests/test_jobs.py
git commit -m "feat(temps3): registre de jobs d'ingestion (threads + polling)"
```

---

### Task 9: Ingestion en tâche de fond (web start/progress + JS)

**Files:**
- Modify: `app/main.py`
- Modify: `app/ui/templates/accueil.html`
- Modify: `app/ui/templates/retro.html`
- Test: `tests/test_jobs_web.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_jobs_web.py`:

```python
import time

from fastapi.testclient import TestClient

from app.main import creer_app, get_extractor, get_retro_extractor
from app.temps1.extraction_ia import MockExtractor
from app.temps1.schemas import EnteteFacture, FactureExtraite, LigneFacture
from app.temps2.schemas import RetroEntete, RetroExtrait, RetroLigne


def _facture():
    return FactureExtraite(
        type_document="facture_marchandise",
        entete=EnteteFacture(labo="URGO", date_facture="2026-01-10", total_ht_affiche=10.0),
        lignes=[LigneFacture(code="3400930000007", designation="X", prix_brut=6.0,
                             remise_pct=10.0, prix_net=5.0, montant_ht=10.0)])


def _retro():
    return RetroExtrait(type_document="retro_lgo",
                        entete=RetroEntete(pharmacie_emettrice="A", pharmacie_destinataire="B"),
                        lignes=[RetroLigne(designation="X", code="3400930000007", qte=1, tva=10.0,
                                           bl_numero="BL1", bl_date="01/08/2025")])


def _attendre_fin(client, url_progress, job_id):
    for _ in range(50):
        j = client.get(f"{url_progress}/{job_id}").json()
        if j.get("termine"):
            return j
        time.sleep(0.1)
    raise AssertionError("job non terminé")


def test_ingest_start_et_progress_labo(tmp_path):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_extractor] = lambda: MockExtractor(defaut=_facture())
    client = TestClient(app)
    r = client.post("/ingest/start",
                    files=[("fichiers", ("f.pdf", b"%PDF", "application/pdf"))]).json()
    assert r["total"] == 1 and "job_id" in r
    j = _attendre_fin(client, "/ingest/progress", r["job_id"])
    assert j["fait"] == 1
    assert j["details"][0]["statut"] == "ingeree"


def test_retro_start_et_progress(tmp_path):
    app = creer_app(db_path=str(tmp_path / "web.db"))
    app.dependency_overrides[get_retro_extractor] = lambda: MockExtractor(defaut=_retro())
    client = TestClient(app)
    r = client.post("/retro/ingest/start",
                    files=[("fichiers", ("r.pdf", b"%PDF", "application/pdf"))]).json()
    assert r["total"] == 1
    j = _attendre_fin(client, "/retro/progress", r["job_id"])
    assert j["fait"] == 1
    assert "n_lignes" in j["details"][0]


def test_progress_job_inconnu(tmp_path):
    client = TestClient(creer_app(db_path=str(tmp_path / "web.db")))
    assert client.get("/ingest/progress/zzz").json() == {"introuvable": True}
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_jobs_web.py -v`
Expected: FAIL (routes absentes).

- [ ] **Step 3: Modifier `app/main.py`**

(a) Ajouter l'import après les imports `app.temps3` :

```python
from app.jobs import RegistreJobs, lancer_job
```

(b) Dans `creer_app`, juste après `app.state.config = charger_config()`, ajouter :

```python
    app.state.jobs = RegistreJobs()
    app.state.jobs_retro = RegistreJobs()
```

(c) Ajouter ces helpers + routes dans `creer_app`, juste avant les routes favicon :

```python
    def _enregistrer_temp(fichiers):
        paires = []
        for f in fichiers:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(f.file.read())
                chemin = tmp.name
            paires.append((f.filename, chemin))
        return paires

    def _traiter_fichier_labo(nom, chemin, extractor):
        try:
            pdf = lire_pdf(chemin)
            pdf.nom = nom
            res = traiter_facture(conn(), pdf, extractor, app.state.config)
            out = {"statut": res.statut, "motif": res.motif,
                   "n_referentiel": res.n_referentiel, "cout": round(res.cout, 5)}
        except Exception as e:
            out = {"statut": "erreur", "motif": f"extraction impossible : {e}",
                   "n_referentiel": 0, "cout": 0.0}
        finally:
            Path(chemin).unlink(missing_ok=True)
        out.update({"fichier": nom, "n_total": _nombre_factures(), "cout_total": _cout_total()})
        return out

    def _traiter_fichier_retro(nom, chemin, extractor):
        try:
            pdf = lire_pdf(chemin)
            pdf.nom = nom
            res = traiter_retro(conn(), pdf, extractor, app.state.config)
            out = {"statut": "ok", "n_lignes": res.n_lignes, "n_resolu": res.n_resolu,
                   "n_orange": res.n_orange, "n_rouge": res.n_rouge, "cout": round(res.cout, 5)}
        except Exception as e:
            out = {"statut": "erreur", "motif": f"extraction impossible : {e}",
                   "n_lignes": 0, "n_resolu": 0, "n_orange": 0, "n_rouge": 0, "cout": 0.0}
        finally:
            Path(chemin).unlink(missing_ok=True)
        out.update({"fichier": nom, "n_total": _nombre_retro(),
                    "cout_total": _cout_total_retro()})
        return out

    @app.post("/ingest/start")
    def ingest_start(fichiers: list[UploadFile], extractor=Depends(get_extractor)):
        paires = _enregistrer_temp(fichiers)
        job_id = app.state.jobs.creer(len(paires))
        lancer_job(app.state.jobs, job_id, paires,
                   lambda n, c: _traiter_fichier_labo(n, c, extractor))
        return {"job_id": job_id, "total": len(paires)}

    @app.get("/ingest/progress/{job_id}")
    def ingest_progress(job_id: str):
        j = app.state.jobs.lire(job_id)
        return j if j is not None else {"introuvable": True}

    @app.post("/retro/ingest/start")
    def retro_start(fichiers: list[UploadFile], extractor=Depends(get_retro_extractor)):
        paires = _enregistrer_temp(fichiers)
        job_id = app.state.jobs_retro.creer(len(paires))
        lancer_job(app.state.jobs_retro, job_id, paires,
                   lambda n, c: _traiter_fichier_retro(n, c, extractor))
        return {"job_id": job_id, "total": len(paires)}

    @app.get("/retro/progress/{job_id}")
    def retro_progress(job_id: str):
        j = app.state.jobs_retro.lire(job_id)
        return j if j is not None else {"introuvable": True}
```

- [ ] **Step 4: Remplacer le `<script>` de `app/ui/templates/accueil.html`**

Remplacer entièrement le bloc `<script> … </script>` existant de `accueil.html` par :

```html
<script>
(function () {
  const form = document.getElementById("form-ingest");
  const input = document.getElementById("input-fichiers");
  const CLE = "retrobuddy_job_ingest";
  const td = (txt, cls) => { const c = document.createElement("td"); c.textContent = txt; if (cls) c.className = cls; return c; };

  function rendre(j) {
    const t = { ingeree: 0, ignoree: 0, en_revue: 0, erreur: 0 };
    const liste = document.getElementById("liste");
    liste.innerHTML = "";
    let cout = 0;
    for (const r of j.details) {
      t[r.statut] = (t[r.statut] || 0) + 1;
      cout += (r.cout || 0);
      if (r.n_total != null) document.getElementById("n-base").textContent = r.n_total;
      if (r.cout_total != null) document.getElementById("cout-base").textContent = Number(r.cout_total).toFixed(4);
      const tr = document.createElement("tr");
      tr.appendChild(td(r.fichier)); tr.appendChild(td(r.statut, r.statut));
      tr.appendChild(td((r.cout || 0).toFixed(5))); tr.appendChild(td(r.motif || ""));
      liste.appendChild(tr);
    }
    document.getElementById("compteur").textContent = j.fait + " / " + j.total;
    document.getElementById("barre").style.width = (j.total ? Math.round(100 * j.fait / j.total) : 0) + "%";
    document.getElementById("recap").textContent =
      "Ingérées " + t.ingeree + " · Ignorées " + t.ignoree + " · En revue " + t.en_revue +
      " · Erreurs " + t.erreur + " · Coût du lot : $" + cout.toFixed(4);
  }

  async function suivre(jobId) {
    document.getElementById("progress").style.display = "block";
    while (true) {
      const j = await (await fetch("/ingest/progress/" + jobId)).json();
      if (j.introuvable) { localStorage.removeItem(CLE); return; }
      rendre(j);
      if (j.termine) { localStorage.removeItem(CLE); return; }
      await new Promise(r => setTimeout(r, 1000));
    }
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!input.files.length) return;
    const fd = new FormData();
    for (const f of input.files) fd.append("fichiers", f);
    const r = await (await fetch("/ingest/start", { method: "POST", body: fd })).json();
    localStorage.setItem(CLE, r.job_id);
    suivre(r.job_id);
  });

  // reprise : si un job tournait, on réaffiche sa progression au chargement
  const enCours = localStorage.getItem(CLE);
  if (enCours) suivre(enCours);
})();
</script>
```

- [ ] **Step 5: Remplacer le `<script>` de `app/ui/templates/retro.html`**

Remplacer entièrement le bloc `<script> … </script>` existant de `retro.html` par :

```html
<script>
(function () {
  const form = document.getElementById("form-retro");
  const input = document.getElementById("input-fichiers");
  const CLE = "retrobuddy_job_retro";
  const td = (txt, cls) => { const c = document.createElement("td"); c.textContent = txt; if (cls) c.className = cls; return c; };

  function rendre(j) {
    const liste = document.getElementById("liste");
    liste.innerHTML = "";
    let cout = 0, resolu = 0, rouge = 0;
    for (const r of j.details) {
      cout += (r.cout || 0); resolu += (r.n_resolu || 0); rouge += (r.n_rouge || 0);
      if (r.n_total != null) document.getElementById("n-base").textContent = r.n_total;
      if (r.cout_total != null) document.getElementById("cout-base").textContent = Number(r.cout_total).toFixed(4);
      const tr = document.createElement("tr");
      tr.appendChild(td(r.fichier));
      tr.appendChild(td(String(r.n_lignes || 0)));
      tr.appendChild(td(String(r.n_resolu || 0), "ingeree"));
      tr.appendChild(td(String(r.n_rouge || 0), "en_revue"));
      tr.appendChild(td((r.cout || 0).toFixed(5)));
      liste.appendChild(tr);
    }
    document.getElementById("compteur").textContent = j.fait + " / " + j.total;
    document.getElementById("barre").style.width = (j.total ? Math.round(100 * j.fait / j.total) : 0) + "%";
    document.getElementById("recap").textContent =
      "Résolues " + resolu + " · Rouges " + rouge + " · Coût du lot : $" + cout.toFixed(4);
  }

  async function suivre(jobId) {
    document.getElementById("progress").style.display = "block";
    while (true) {
      const j = await (await fetch("/retro/progress/" + jobId)).json();
      if (j.introuvable) { localStorage.removeItem(CLE); return; }
      rendre(j);
      if (j.termine) { localStorage.removeItem(CLE); return; }
      await new Promise(r => setTimeout(r, 1000));
    }
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!input.files.length) return;
    const fd = new FormData();
    for (const f of input.files) fd.append("fichiers", f);
    const r = await (await fetch("/retro/ingest/start", { method: "POST", body: fd })).json();
    localStorage.setItem(CLE, r.job_id);
    suivre(r.job_id);
  });

  const enCours = localStorage.getItem(CLE);
  if (enCours) suivre(enCours);
})();
</script>
```

> Note : l'attribut `name` de l'input passe de `fichier` à `fichiers` (multi). Vérifier que
> `accueil.html` et `retro.html` ont bien `name="fichiers"` sur l'input fichier (l'`accueil`
> l'a déjà ; pour `retro.html`, changer `name="fichier"` en `name="fichiers"` à l'étape 5).

- [ ] **Step 6: Ajuster l'input de `retro.html`**

Dans `app/ui/templates/retro.html`, remplacer `name="fichier"` par `name="fichiers"` sur la balise `<input type="file" …>`.

- [ ] **Step 7: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_jobs_web.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Lancer toute la suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tous les unitaires verts ; intégration deselected.

- [ ] **Step 9: Commit**

```bash
git add app/main.py app/ui/templates/accueil.html app/ui/templates/retro.html tests/test_jobs_web.py
git commit -m "feat(temps3): ingestion en tache de fond (job serveur + polling + reprise localStorage)"
```

---

### Task 10: Vérification finale + validation réelle

**Files:** aucun (vérification).

- [ ] **Step 1: Suite complète**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tous les unitaires verts ; tests d'intégration deselected.

- [ ] **Step 2: Démarrer l'app et vérifier les pages**

Run: `.venv/Scripts/python -m uvicorn app.main:app --reload`
Ouvrir `http://127.0.0.1:8000/resolution`, `/retro`, `/` — les pages répondent ; la nav contient « Résolution ».

- [ ] **Step 3: Validation réelle (avec l'utilisateur)**

- Ingérer les **factures labo** correspondant aux produits du LGO (onglet Import labo), puis la
  **facture LGO** (onglet Rétrocession). Vérifier dans `/resolution` que des lignes passent en
  orange (candidat par désignation) et que « Re-rapprocher » réduit les rouges.
- Pendant une ingestion, **changer d'onglet puis revenir** sur la page d'import : la progression
  doit toujours être là et continuer.

---

## Self-Review (couverture du spec)

- §2 matching désignation (normalisation, score, resoudre_par_designation, intégration, rematch)
  → Tasks 1, 2, 4, 5. ✅
- §3 tableau de résolution (page, compteurs, couleurs, édition inline, accepter/refuser, recalcul
  net, rematch) → Tasks 6, 7. ✅
- §4 ingestion en tâche de fond (registre, threads, start/progress, reprise localStorage) →
  Tasks 8, 9. ✅
- §5 config seuils → Task 3. ✅
- §6 tests → chaque task. ✅
- §7 gestion d'erreurs (job continue, refuser → rouge, job inconnu) → Tasks 8, 6, 9. ✅
- §8 critères d'acceptation → couverts par Tasks 1-9 + validation Task 10.

Cohérence des types : `normaliser_designation`/`score_designation`/`extraire_dosage`/
`dosages_concordants`/`charger_abreviations` (Task 1) ; `resoudre_par_designation` →
`(code, desig, score)` (Task 2) ; `ResultatRetro` + `n_orange` (Task 4) ; `rematcher` → dict
compteurs (Task 5) ; `calcul_net`/`enregistrer_ligne`/`accepter_orange`/`refuser_orange` (Task 6) ;
`RegistreJobs`/`lancer_job` (Task 8). Endpoints `/resolution*`, `/ingest/start`,
`/ingest/progress/{id}`, `/retro/ingest/start`, `/retro/progress/{id}` (Tasks 7, 9).
