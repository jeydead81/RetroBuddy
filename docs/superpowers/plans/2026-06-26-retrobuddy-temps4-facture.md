# RetroBuddy — Temps 4 (Édition de la facture de rétrocession) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire la facture de rétrocession (regroupée par BL, ventilation TVA, totaux) à partir des lignes résolues, l'afficher et l'exporter en PDF / Excel / CSV, génération bloquée tant qu'une ligne non résolue subsiste.

**Architecture:** Un cœur de calcul pur (`facture_builder`) qui dérive un objet `Facture` de `retro_documents` + `retro_lignes` (testable sans I/O), trois sérialiseurs (CSV stdlib, XLSX openpyxl, PDF reportlab) qui produisent des bytes, et une page web FastAPI `/facture/{retro_id}` + endpoints de téléchargement.

**Tech Stack:** Python 3.13, SQLite, FastAPI, `reportlab`, `openpyxl`, pytest.

**Spec de référence :** `docs/superpowers/specs/2026-06-26-retrobuddy-temps4-facture-design.md`.

---

## Conventions

- Chemins relatifs à `C:\Users\pharma01\Desktop\RetroBuddy`. Python/pytest via `.venv/Scripts/python`.
- Tests unitaires : aucun appel API. Tables `retro_documents`, `retro_lignes` existantes.

---

### Task 1: Dépendances (reportlab, openpyxl)

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Ajouter les dépendances à `requirements.txt`**

Ajouter ces deux lignes à la fin de `requirements.txt` :
```
reportlab>=4.0
openpyxl>=3.1
```

- [ ] **Step 2: Installer**

Run: `.venv/Scripts/python -m pip install -r requirements.txt`
Expected: installation de `reportlab` et `openpyxl` sans erreur.

- [ ] **Step 3: Vérifier l'import**

Run: `.venv/Scripts/python -c "import reportlab, openpyxl; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(temps4): dependances reportlab + openpyxl"
```

---

### Task 2: Construction de la facture (`temps4/facture_builder.py`)

**Files:**
- Create: `app/temps4/__init__.py`
- Create: `app/temps4/facture_builder.py`
- Test: `tests/test_facture_builder.py`

- [ ] **Step 1: Créer le package**

Créer le fichier vide `app/temps4/__init__.py`.

- [ ] **Step 2: Écrire le test**

Create `tests/test_facture_builder.py`:

```python
from app.db import get_connection, init_db
from app.temps4.facture_builder import construire_facture


def _conn(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    return conn


def _doc(conn):
    cur = conn.execute(
        "INSERT INTO retro_documents (pharmacie_emettrice, pharmacie_destinataire, "
        "numero, date_vente) VALUES ('SERALY', 'CENON', 'N1', '22/09/2025')")
    return cur.lastrowid


def _ligne(conn, retro_id, designation, qte, prix_net, tva, bl_numero, bl_date,
           statut="resolu"):
    conn.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, qte, prix_brut, remise_pct, "
        "prix_net, tva, bl_numero, bl_date, statut_ecart) "
        "VALUES (?, ?, 'C', ?, ?, 10.0, ?, ?, ?, ?, ?)",
        (retro_id, designation, qte, (prix_net + 1), prix_net, tva, bl_numero, bl_date, statut))
    conn.commit()


def test_regroupement_par_bl_et_montant_ht(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    _ligne(conn, rid, "A", 2, 5.0, 10.0, "BL1", "01/08/2025")
    _ligne(conn, rid, "B", 1, 4.0, 10.0, "BL1", "01/08/2025")
    _ligne(conn, rid, "C", 3, 2.0, 20.0, "BL2", "04/08/2025")
    f = construire_facture(conn, rid)
    assert f.emettrice == "SERALY"
    assert len(f.groupes) == 2
    assert f.groupes[0].bl_numero == "BL1"
    assert len(f.groupes[0].lignes) == 2
    assert f.groupes[0].lignes[0].montant_ht == 10.0   # 2 * 5.0
    assert f.groupes[1].lignes[0].montant_ht == 6.0    # 3 * 2.0


def test_ventilation_tva_et_totaux(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    _ligne(conn, rid, "A", 2, 5.0, 10.0, "BL1", "01/08/2025")   # HT 10, TVA 10%
    _ligne(conn, rid, "C", 3, 2.0, 20.0, "BL2", "04/08/2025")   # HT 6, TVA 20%
    f = construire_facture(conn, rid)
    assert f.total_ht == 16.0
    taux = {v.taux: v for v in f.ventilation}
    assert taux[10.0].base_ht == 10.0
    assert taux[10.0].montant_tva == 1.0      # 10 * 10%
    assert taux[20.0].montant_tva == 1.2      # 6 * 20%
    assert f.total_tva == 2.2
    assert f.total_ttc == 18.2


def test_exclut_les_rouges_et_bloque(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    _ligne(conn, rid, "A", 2, 5.0, 10.0, "BL1", "01/08/2025", statut="resolu")
    conn.execute("INSERT INTO retro_lignes (retro_id, designation, qte, tva, bl_numero, "
                 "bl_date, statut_ecart) VALUES (?, 'ROUGE', 1, 10.0, 'BL1', '01/08/2025', 'rouge')",
                 (rid,))
    conn.commit()
    f = construire_facture(conn, rid)
    assert f.bloquee is True
    assert f.n_rouge == 1
    # la ligne rouge n'apparaît pas
    designations = [l.designation for g in f.groupes for l in g.lignes]
    assert designations == ["A"]


def test_non_bloquee_si_tout_resolu(tmp_path):
    conn = _conn(tmp_path)
    rid = _doc(conn)
    _ligne(conn, rid, "A", 2, 5.0, 10.0, "BL1", "01/08/2025")
    f = construire_facture(conn, rid)
    assert f.bloquee is False
    assert f.n_rouge == 0


def test_retro_id_inconnu_renvoie_none(tmp_path):
    assert construire_facture(_conn(tmp_path), 999) is None
```

- [ ] **Step 3: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_facture_builder.py -v`
Expected: FAIL (module absent).

- [ ] **Step 4: Implémenter `app/temps4/facture_builder.py`**

```python
from dataclasses import dataclass


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
    lignes: list


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
    groupes: list
    ventilation: list
    total_ht: float
    total_tva: float
    total_ttc: float
    bloquee: bool
    n_rouge: int


def construire_facture(conn, retro_id):
    doc = conn.execute(
        "SELECT pharmacie_emettrice, pharmacie_destinataire, numero, date_vente "
        "FROM retro_documents WHERE id = ?", (retro_id,)).fetchone()
    if doc is None:
        return None

    lignes = conn.execute(
        "SELECT designation, code, qte, prix_brut, remise_pct, prix_net, tva, "
        "bl_numero, bl_date, statut_ecart FROM retro_lignes WHERE retro_id = ? ORDER BY id",
        (retro_id,)).fetchall()
    n_rouge = sum(1 for l in lignes if l["statut_ecart"] == "rouge")

    groupes = []
    courant = None
    total_ht = 0.0
    bases = {}
    for l in lignes:
        if l["statut_ecart"] == "rouge":
            continue
        qte = l["qte"] or 0
        prix_net = l["prix_net"] or 0
        montant = round(qte * prix_net, 2)
        total_ht = round(total_ht + montant, 2)
        taux = l["tva"] if l["tva"] is not None else 0.0
        bases[taux] = round(bases.get(taux, 0.0) + montant, 2)
        lf = LigneFacturee(l["designation"], l["code"], qte, l["prix_brut"],
                           l["remise_pct"], prix_net, l["tva"], montant)
        cle = (l["bl_numero"], l["bl_date"])
        if courant is None or (courant.bl_numero, courant.bl_date) != cle:
            courant = GroupeBL(l["bl_numero"], l["bl_date"], [])
            groupes.append(courant)
        courant.lignes.append(lf)

    ventilation = []
    total_tva = 0.0
    for taux in sorted(bases):
        tva = round(bases[taux] * taux / 100, 2)
        total_tva = round(total_tva + tva, 2)
        ventilation.append(VentilationTva(taux, bases[taux], tva))
    total_ttc = round(total_ht + total_tva, 2)

    return Facture(retro_id, doc["pharmacie_emettrice"], doc["pharmacie_destinataire"],
                   doc["numero"], doc["date_vente"], groupes, ventilation,
                   total_ht, total_tva, total_ttc, n_rouge > 0, n_rouge)
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_facture_builder.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add app/temps4/__init__.py app/temps4/facture_builder.py tests/test_facture_builder.py
git commit -m "feat(temps4): construction de la facture (regroupement BL, ventilation TVA, totaux, blocage)"
```

---

### Task 3: Export CSV (`temps4/export_csv.py`)

**Files:**
- Create: `app/temps4/export_csv.py`
- Test: `tests/test_export_csv.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_export_csv.py`:

```python
from app.temps4.export_csv import facture_csv
from app.temps4.facture_builder import (
    Facture, GroupeBL, LigneFacturee, VentilationTva)


def _facture():
    ligne = LigneFacturee("PRODUIT A", "C1", 2, 6.0, 10.0, 5.0, 10.0, 10.0)
    return Facture(
        retro_id=1, emettrice="SERALY", destinataire="CENON", numero="N1",
        date_vente="22/09/2025",
        groupes=[GroupeBL("BL1", "01/08/2025", [ligne])],
        ventilation=[VentilationTva(10.0, 10.0, 1.0)],
        total_ht=10.0, total_tva=1.0, total_ttc=11.0, bloquee=False, n_rouge=0)


def test_csv_contient_entete_ligne_et_total():
    csv = facture_csv(_facture())
    assert "SERALY" in csv
    assert "PRODUIT A" in csv
    assert "Total TTC" in csv
    assert "11.0" in csv
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_export_csv.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/temps4/export_csv.py`**

```python
import csv
import io


def facture_csv(facture):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Facture de rétrocession", facture.numero or ""])
    w.writerow(["Émettrice", facture.emettrice or ""])
    w.writerow(["Destinataire", facture.destinataire or ""])
    w.writerow(["Date", facture.date_vente or ""])
    w.writerow([])
    w.writerow(["BL", "Date BL", "Désignation", "Code", "Qté", "PA brut",
                "Remise %", "PA net", "TVA", "Montant HT"])
    for g in facture.groupes:
        for l in g.lignes:
            w.writerow([g.bl_numero or "", g.bl_date or "", l.designation, l.code or "",
                        l.qte, "" if l.prix_brut is None else l.prix_brut,
                        "" if l.remise_pct is None else l.remise_pct, l.prix_net,
                        "" if l.tva is None else l.tva, l.montant_ht])
    w.writerow([])
    w.writerow(["Ventilation TVA", "Taux", "Base HT", "Montant TVA"])
    for v in facture.ventilation:
        w.writerow(["", v.taux, v.base_ht, v.montant_tva])
    w.writerow([])
    w.writerow(["Total HT", facture.total_ht])
    w.writerow(["Total TVA", facture.total_tva])
    w.writerow(["Total TTC", facture.total_ttc])
    return "﻿" + buf.getvalue()   # BOM pour Excel
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_export_csv.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add app/temps4/export_csv.py tests/test_export_csv.py
git commit -m "feat(temps4): export CSV de la facture"
```

---

### Task 4: Export XLSX (`temps4/export_xlsx.py`)

**Files:**
- Create: `app/temps4/export_xlsx.py`
- Test: `tests/test_export_xlsx.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_export_xlsx.py`:

```python
from app.temps4.export_xlsx import facture_xlsx
from app.temps4.facture_builder import (
    Facture, GroupeBL, LigneFacturee, VentilationTva)


def _facture():
    ligne = LigneFacturee("PRODUIT A", "C1", 2, 6.0, 10.0, 5.0, 10.0, 10.0)
    return Facture(
        retro_id=1, emettrice="SERALY", destinataire="CENON", numero="N1",
        date_vente="22/09/2025",
        groupes=[GroupeBL("BL1", "01/08/2025", [ligne])],
        ventilation=[VentilationTva(10.0, 10.0, 1.0)],
        total_ht=10.0, total_tva=1.0, total_ttc=11.0, bloquee=False, n_rouge=0)


def test_xlsx_renvoie_des_bytes_zip():
    data = facture_xlsx(_facture())
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert data[:2] == b"PK"      # un .xlsx est un zip
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_export_xlsx.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/temps4/export_xlsx.py`**

```python
import io

from openpyxl import Workbook
from openpyxl.styles import Font


def facture_xlsx(facture):
    wb = Workbook()
    ws = wb.active
    ws.title = "Facture"
    gras = Font(bold=True)

    ws.append(["Facture de rétrocession", facture.numero or ""])
    ws.append(["Émettrice", facture.emettrice or ""])
    ws.append(["Destinataire", facture.destinataire or ""])
    ws.append(["Date", facture.date_vente or ""])
    ws.append([])

    ws.append(["BL", "Date BL", "Désignation", "Code", "Qté", "PA brut", "Remise %",
               "PA net", "TVA", "Montant HT"])
    for cell in ws[ws.max_row]:
        cell.font = gras
    for g in facture.groupes:
        for l in g.lignes:
            ws.append([g.bl_numero, g.bl_date, l.designation, l.code, l.qte, l.prix_brut,
                       l.remise_pct, l.prix_net, l.tva, l.montant_ht])

    ws.append([])
    ws.append(["Ventilation TVA", "Taux", "Base HT", "Montant TVA"])
    for v in facture.ventilation:
        ws.append(["", v.taux, v.base_ht, v.montant_tva])

    ws.append([])
    for libelle, val in (("Total HT", facture.total_ht), ("Total TVA", facture.total_tva),
                         ("Total TTC", facture.total_ttc)):
        ws.append([libelle, val])
        ws[ws.max_row][0].font = gras

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_export_xlsx.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add app/temps4/export_xlsx.py tests/test_export_xlsx.py
git commit -m "feat(temps4): export XLSX de la facture"
```

---

### Task 5: Export PDF (`temps4/export_pdf.py`)

**Files:**
- Create: `app/temps4/export_pdf.py`
- Test: `tests/test_export_pdf.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_export_pdf.py`:

```python
from app.temps4.export_pdf import facture_pdf
from app.temps4.facture_builder import (
    Facture, GroupeBL, LigneFacturee, VentilationTva)


def _facture():
    ligne = LigneFacturee("PRODUIT A", "C1", 2, 6.0, 10.0, 5.0, 10.0, 10.0)
    return Facture(
        retro_id=1, emettrice="SERALY", destinataire="CENON", numero="N1",
        date_vente="22/09/2025",
        groupes=[GroupeBL("BL1", "01/08/2025", [ligne])],
        ventilation=[VentilationTva(10.0, 10.0, 1.0)],
        total_ht=10.0, total_tva=1.0, total_ttc=11.0, bloquee=False, n_rouge=0)


def test_pdf_renvoie_des_bytes_pdf():
    data = facture_pdf(_facture())
    assert isinstance(data, bytes)
    assert data[:4] == b"%PDF"
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_export_pdf.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `app/temps4/export_pdf.py`**

```python
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def facture_pdf(facture):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    el = []

    el.append(Paragraph(f"Facture de rétrocession {facture.numero or ''}", styles["Title"]))
    el.append(Paragraph(f"Émettrice : {facture.emettrice or ''}", styles["Normal"]))
    el.append(Paragraph(f"Destinataire : {facture.destinataire or ''}", styles["Normal"]))
    el.append(Paragraph(f"Date : {facture.date_vente or ''}", styles["Normal"]))
    el.append(Spacer(1, 6 * mm))

    entete = ["Désignation", "Code", "Qté", "PA brut", "Rem.%", "PA net", "TVA", "Montant HT"]
    for g in facture.groupes:
        el.append(Paragraph(
            f"Bon livraison {g.bl_numero or ''} du {g.bl_date or ''}", styles["Heading4"]))
        data = [entete]
        for l in g.lignes:
            data.append([l.designation, l.code or "", l.qte, l.prix_brut, l.remise_pct,
                         l.prix_net, l.tva, l.montant_ht])
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ]))
        el.append(t)
        el.append(Spacer(1, 3 * mm))

    el.append(Spacer(1, 4 * mm))
    vent = [["Taux TVA", "Base HT", "Montant TVA"]]
    for v in facture.ventilation:
        vent.append([v.taux, v.base_ht, v.montant_tva])
    tv = Table(vent)
    tv.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    el.append(tv)
    el.append(Spacer(1, 3 * mm))

    el.append(Paragraph(f"Total HT : {facture.total_ht}", styles["Normal"]))
    el.append(Paragraph(f"Total TVA : {facture.total_tva}", styles["Normal"]))
    el.append(Paragraph(f"<b>Total TTC : {facture.total_ttc}</b>", styles["Normal"]))

    doc.build(el)
    return buf.getvalue()
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_export_pdf.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add app/temps4/export_pdf.py tests/test_export_pdf.py
git commit -m "feat(temps4): export PDF de la facture (reportlab)"
```

---

### Task 6: Page facture + téléchargements (web)

**Files:**
- Modify: `app/main.py`
- Create: `app/ui/templates/factures_retro.html`
- Create: `app/ui/templates/facture.html`
- Modify: `app/ui/templates/base.html`
- Test: `tests/test_facture_web.py`

- [ ] **Step 1: Écrire le test**

Create `tests/test_facture_web.py`:

```python
from fastapi.testclient import TestClient

from app.main import creer_app


def _client(tmp_path):
    return TestClient(creer_app(db_path=str(tmp_path / "web.db")))


def _doc(client):
    from app.db import get_connection
    conn = get_connection(client.app.state.db_path)
    cur = conn.execute(
        "INSERT INTO retro_documents (pharmacie_emettrice, pharmacie_destinataire, numero) "
        "VALUES ('SERALY', 'CENON', 'N1')")
    rid = cur.lastrowid
    conn.commit()
    return conn, rid


def _ligne(conn, rid, statut="resolu", prix_net=5.0):
    conn.execute(
        "INSERT INTO retro_lignes (retro_id, designation, code, qte, prix_brut, remise_pct, "
        "prix_net, tva, bl_numero, bl_date, statut_ecart) "
        "VALUES (?, 'PRODUIT A', 'C', 2, 6.0, 10.0, ?, 10.0, 'BL1', '01/08/2025', ?)",
        (rid, prix_net, statut))
    conn.commit()


def test_factures_retro_200(tmp_path):
    assert _client(tmp_path).get("/factures-retro").status_code == 200


def test_facture_apercu_200(tmp_path):
    client = _client(tmp_path)
    conn, rid = _doc(client)
    _ligne(conn, rid)
    r = client.get(f"/facture/{rid}")
    assert r.status_code == 200
    assert "PRODUIT A" in r.text


def test_facture_csv_non_bloquee(tmp_path):
    client = _client(tmp_path)
    conn, rid = _doc(client)
    _ligne(conn, rid)
    r = client.get(f"/facture/{rid}/csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "PRODUIT A" in r.text


def test_facture_pdf_bloquee_renvoie_409(tmp_path):
    client = _client(tmp_path)
    conn, rid = _doc(client)
    _ligne(conn, rid, statut="resolu")
    _ligne(conn, rid, statut="rouge", prix_net=0.0)
    assert client.get(f"/facture/{rid}/pdf").status_code == 409


def test_facture_inconnue_404(tmp_path):
    assert _client(tmp_path).get("/facture/999/csv").status_code == 404
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `.venv/Scripts/python -m pytest tests/test_facture_web.py -v`
Expected: FAIL (routes absentes).

- [ ] **Step 3: Modifier `app/main.py`**

(a) Ajouter en haut, après l'import `from app.temps3.rematch import rematcher` :
```python
from fastapi import HTTPException
from fastapi.responses import Response
from app.temps4.export_csv import facture_csv
from app.temps4.export_pdf import facture_pdf
from app.temps4.export_xlsx import facture_xlsx
from app.temps4.facture_builder import construire_facture
```
> Note : `HTTPException` et `Response` viennent de `fastapi`/`fastapi.responses` ; si une
> ligne d'import `from fastapi import ...` existe déjà, ajouter `HTTPException` à cette ligne
> plutôt qu'un import séparé (les deux fonctionnent).

(b) À l'intérieur de `creer_app`, juste avant les routes favicon, ajouter :
```python
    def _facture_ou_404(retro_id):
        f = construire_facture(conn(), retro_id)
        if f is None:
            raise HTTPException(status_code=404, detail="facture introuvable")
        return f

    @app.get("/factures-retro", response_class=HTMLResponse)
    def factures_retro(request: Request):
        rows = conn().execute(
            "SELECT d.id, d.numero, d.pharmacie_emettrice, d.pharmacie_destinataire, "
            "COUNT(l.id) n_lignes, "
            "SUM(CASE WHEN l.statut_ecart='rouge' THEN 1 ELSE 0 END) n_rouge "
            "FROM retro_documents d LEFT JOIN retro_lignes l ON l.retro_id = d.id "
            "GROUP BY d.id ORDER BY d.id DESC").fetchall()
        return TEMPLATES.TemplateResponse(request, "factures_retro.html", {"rows": rows})

    @app.get("/facture/{retro_id}", response_class=HTMLResponse)
    def facture(request: Request, retro_id: int):
        f = _facture_ou_404(retro_id)
        return TEMPLATES.TemplateResponse(request, "facture.html", {"f": f})

    @app.get("/facture/{retro_id}/csv")
    def facture_dl_csv(retro_id: int):
        f = _facture_ou_404(retro_id)
        if f.bloquee:
            raise HTTPException(status_code=409, detail="lignes à compléter")
        return Response(
            content=facture_csv(f), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=facture_{retro_id}.csv"})

    @app.get("/facture/{retro_id}/xlsx")
    def facture_dl_xlsx(retro_id: int):
        f = _facture_ou_404(retro_id)
        if f.bloquee:
            raise HTTPException(status_code=409, detail="lignes à compléter")
        return Response(
            content=facture_xlsx(f),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=facture_{retro_id}.xlsx"})

    @app.get("/facture/{retro_id}/pdf")
    def facture_dl_pdf(retro_id: int):
        f = _facture_ou_404(retro_id)
        if f.bloquee:
            raise HTTPException(status_code=409, detail="lignes à compléter")
        return Response(
            content=facture_pdf(f), media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=facture_{retro_id}.pdf"})
```

- [ ] **Step 4: Ajouter le lien nav dans `app/ui/templates/base.html`**

Dans la ligne `<nav>`, ajouter `<a href="/factures-retro">Factures rétro</a>` juste après le lien `Résolution`. La ligne devient :
```html
    <a href="/">Import labo</a><a href="/referentiel">Référentiel</a><a href="/factures">Factures</a><a href="/retro">Rétrocession</a><a href="/retro-lignes">Lignes rétro</a><a href="/resolution">Résolution</a><a href="/factures-retro">Factures rétro</a>
```

- [ ] **Step 5: Créer `app/ui/templates/factures_retro.html`**

```html
{% extends "base.html" %}
{% block contenu %}
<h1>Factures de rétrocession</h1>
<table>
  <tr><th>#</th><th>Numéro</th><th>Émettrice</th><th>Destinataire</th><th>Lignes</th><th>À compléter</th><th></th></tr>
  {% for r in rows %}
    <tr>
      <td>{{ r["id"] }}</td><td>{{ r["numero"] }}</td>
      <td>{{ r["pharmacie_emettrice"] }}</td><td>{{ r["pharmacie_destinataire"] }}</td>
      <td>{{ r["n_lignes"] }}</td>
      <td class="{{ 'en_revue' if r['n_rouge'] else 'ingeree' }}">{{ r["n_rouge"] }}</td>
      <td><a href="/facture/{{ r['id'] }}">Ouvrir</a></td>
    </tr>
  {% endfor %}
</table>
{% endblock %}
```

- [ ] **Step 6: Créer `app/ui/templates/facture.html`**

```html
{% extends "base.html" %}
{% block contenu %}
<h1>Facture {{ f.numero or "" }}</h1>
<p>Émettrice : <strong>{{ f.emettrice or "" }}</strong> →
   Destinataire : <strong>{{ f.destinataire or "" }}</strong> · {{ f.date_vente or "" }}</p>

{% if f.bloquee %}
  <p class="en_revue"><strong>{{ f.n_rouge }} ligne(s) à compléter avant de pouvoir générer la facture.</strong></p>
{% endif %}

<p>
  {% if f.bloquee %}
    <button disabled>Générer PDF</button>
    <button disabled>Générer Excel</button>
    <button disabled>Générer CSV</button>
  {% else %}
    <a href="/facture/{{ f.retro_id }}/pdf"><button>Générer PDF</button></a>
    <a href="/facture/{{ f.retro_id }}/xlsx"><button>Générer Excel</button></a>
    <a href="/facture/{{ f.retro_id }}/csv"><button>Générer CSV</button></a>
  {% endif %}
</p>

{% for g in f.groupes %}
  <h3>Bon livraison {{ g.bl_numero or "" }} du {{ g.bl_date or "" }}</h3>
  <table>
    <tr><th>Désignation</th><th>Code</th><th>Qté</th><th>PA brut</th><th>Remise %</th>
        <th>PA net</th><th>TVA</th><th>Montant HT</th></tr>
    {% for l in g.lignes %}
      <tr><td>{{ l.designation }}</td><td>{{ l.code or "" }}</td><td>{{ l.qte }}</td>
          <td>{{ l.prix_brut if l.prix_brut is not none else "" }}</td>
          <td>{{ l.remise_pct if l.remise_pct is not none else "" }}</td>
          <td>{{ l.prix_net }}</td><td>{{ l.tva if l.tva is not none else "" }}</td>
          <td>{{ l.montant_ht }}</td></tr>
    {% endfor %}
  </table>
{% endfor %}

<h3>Ventilation TVA</h3>
<table>
  <tr><th>Taux TVA</th><th>Base HT</th><th>Montant TVA</th></tr>
  {% for v in f.ventilation %}
    <tr><td>{{ v.taux }}</td><td>{{ v.base_ht }}</td><td>{{ v.montant_tva }}</td></tr>
  {% endfor %}
</table>
<p>Total HT : {{ f.total_ht }} · Total TVA : {{ f.total_tva }} ·
   <strong>Total TTC : {{ f.total_ttc }}</strong></p>
{% endblock %}
```

- [ ] **Step 7: Lancer le test, vérifier le succès**

Run: `.venv/Scripts/python -m pytest tests/test_facture_web.py -v`
Expected: PASS (5 tests).

- [ ] **Step 8: Lancer toute la suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tous les unitaires verts ; intégration deselected.

- [ ] **Step 9: Commit**

```bash
git add app/main.py app/ui/templates/factures_retro.html app/ui/templates/facture.html app/ui/templates/base.html tests/test_facture_web.py
git commit -m "feat(temps4): page facture + telechargements PDF/Excel/CSV (blocage si rouge)"
```

---

### Task 7: Vérification finale + validation réelle

**Files:** aucun (vérification).

- [ ] **Step 1: Suite complète**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tous les unitaires verts ; intégration deselected.

- [ ] **Step 2: Démarrer l'app et générer une facture**

Run: `.venv/Scripts/python -m uvicorn app.main:app --reload`
Ouvrir `http://127.0.0.1:8000/factures-retro`, ouvrir une facture, vérifier l'aperçu (groupes
par BL, ventilation TVA, totaux), et générer PDF / Excel / CSV. Vérifier que les boutons sont
désactivés et les téléchargements renvoient 409 tant qu'une ligne reste à compléter.

---

## Self-Review (couverture du spec)

- §2 lignes facturables / blocage → Task 2 (`construire_facture`, `bloquee`, exclusion rouge). ✅
- §3.1 structures → Task 2 ; §3.2 calcul (BL, montant HT, ventilation, totaux) → Task 2 ;
  §3.3 exports → Tasks 3 (CSV), 4 (XLSX), 5 (PDF). ✅
- §4 web (liste, aperçu, téléchargements, blocage/409, nav) → Task 6. ✅
- §5 dépendances → Task 1. ✅
- §6 tests → chaque task. ✅
- §7 gestion d'erreurs (404 inconnu, 409 bloquée) → Task 6. ✅
- §8 critères d'acceptation → couverts par Tasks 2-6 + validation Task 7.

Cohérence des types : `Facture`/`GroupeBL`/`LigneFacturee`/`VentilationTva` + `construire_facture`
(Task 2) réutilisés par `facture_csv` (Task 3), `facture_xlsx` (Task 4), `facture_pdf` (Task 5),
et les routes `/facture/{retro_id}` + `/facture/{retro_id}/{csv|xlsx|pdf}` (Task 6).
