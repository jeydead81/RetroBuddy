import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import charger_config, enregistrer_cle_api
from app.db import get_connection, init_db
from app.temps1.extraction_ia import ClaudeExtractor
from app.temps1.pdf_reader import lire_pdf
from app.temps1.pipeline import traiter_facture
from app.temps1.referentiel import enregistrer_referentiel
from app.temps1.schemas import LigneFacture
from app.temps2.schemas import RetroExtrait
from app.temps2.traitement_retro import traiter_retro
from app.temps3 import resolution as resolution_logique
from app.temps3.rematch import rematcher
from app.temps4.export_csv import facture_csv
from app.temps4.export_pdf import facture_pdf
from app.temps4.export_xlsx import facture_xlsx
from app.temps4.facture_builder import construire_facture
from app.temps4.recalcul import recalculer_prix_facture
from app.jobs import RegistreJobs, lancer_job

TEMPLATES = Jinja2Templates(directory="app/ui/templates")


def get_extractor():
    cfg = charger_config()
    return ClaudeExtractor(cfg.get("anthropic_api_key", ""))


def get_retro_extractor():
    cfg = charger_config()
    return ClaudeExtractor(cfg.get("anthropic_api_key", ""),
                           prompt_path="prompts/extraction_retro.txt",
                           output_format=RetroExtrait)


def _motif_erreur(e):
    """Traduit une exception d'extraction en message compréhensible pour l'utilisateur."""
    s = str(e).lower()
    if any(k in s for k in ("authentication", "x-api-key", "api_key", "401", "invalid api key")):
        return "clé API invalide ou absente — vérifiez-la dans ⚙ Réglages"
    if any(k in s for k in ("rate limit", "429", "quota", "credit", "insufficient", "billing")):
        return "quota ou crédits API épuisés — vérifiez votre compte Anthropic"
    return f"extraction impossible : {e}"


MOIS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


def _mois_disponibles(c, table, col):
    """Mois présents dans une colonne date JJ/MM/AAAA (value 'AAAA-MM',
    label 'Septembre 2025'), les plus récents d'abord — pour le menu de filtre."""
    vus = {}
    for r in c.execute(f"SELECT DISTINCT {col} d FROM {table} WHERE {col} IS NOT NULL"):
        parts = str(r["d"]).split("/")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit() and len(parts[2]) == 4:
            m = int(parts[1])
            if 1 <= m <= 12:
                vus[f"{parts[2]}-{parts[1].zfill(2)}"] = f"{MOIS_FR[m].capitalize()} {parts[2]}"
    return sorted(vus.items(), reverse=True)


def creer_app(db_path="data/retrocession.db") -> FastAPI:
    app = FastAPI(title="RetroBuddy")
    app.state.db_path = db_path
    app.state.config = charger_config()
    app.state.jobs = RegistreJobs()
    app.state.jobs_retro = RegistreJobs()

    init_db(get_connection(db_path))

    def conn():
        return get_connection(app.state.db_path)

    def _param(cle, defaut="0"):
        r = conn().execute("SELECT valeur FROM parametres WHERE cle=?", (cle,)).fetchone()
        return r["valeur"] if r else defaut

    def _set_param(cle, valeur):
        c = conn()
        c.execute("INSERT INTO parametres(cle, valeur) VALUES (?, ?) "
                  "ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur", (cle, str(valeur)))
        c.commit()

    def _cle_info():
        cle = (charger_config().get("anthropic_api_key") or "").strip()
        masquee = ("…" + cle[-4:]) if len(cle) >= 4 else ("…" if cle else "")
        return bool(cle), masquee

    def _nombre_factures():
        return conn().execute("SELECT COUNT(*) n FROM factures").fetchone()["n"]

    def _cout_total():
        v = conn().execute(
            "SELECT COALESCE(SUM(cout_estime), 0) c FROM factures").fetchone()["c"]
        return round(max(0.0, v - float(_param("cout_baseline_labo", "0"))), 4)

    def _ingerer_un(fichier: UploadFile, extractor):
        """Traite UN PDF et renvoie un dict JSON-able."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(fichier.file.read())
            chemin = tmp.name
        try:
            pdf = lire_pdf(chemin)
            pdf.nom = fichier.filename or pdf.nom
            res = traiter_facture(conn(), pdf, extractor, app.state.config)
            statut, motif, n_ref, cout = res.statut, res.motif, res.n_referentiel, res.cout
        except Exception as e:  # un PDF qui échoue ne doit pas casser le lot
            statut, motif, n_ref, cout = "erreur", _motif_erreur(e), 0, 0.0
        finally:
            Path(chemin).unlink(missing_ok=True)
        return {"fichier": fichier.filename, "statut": statut, "motif": motif,
                "n_referentiel": n_ref, "cout": round(cout, 5),
                "n_total": _nombre_factures(), "cout_total": _cout_total()}

    @app.get("/", response_class=HTMLResponse)
    def accueil(request: Request):
        cle_presente, cle_masquee = _cle_info()
        return TEMPLATES.TemplateResponse(
            request, "home.html",
            {"n_total": _nombre_factures(), "cout_total": _cout_total(),
             "cle_presente": cle_presente, "cle_masquee": cle_masquee})

    @app.get("/import-labos", response_class=HTMLResponse)
    def import_labos(request: Request):
        return TEMPLATES.TemplateResponse(
            request, "import_labos.html",
            {"n_total": _nombre_factures(), "cout_total": _cout_total()})

    @app.post("/ingest-un")
    def ingest_un(fichier: UploadFile, extractor=Depends(get_extractor)):
        """Ingestion d'un seul PDF (appelé en boucle par le JS pour la barre X/N)."""
        return _ingerer_un(fichier, extractor)

    @app.post("/ingest", response_class=HTMLResponse)
    def ingest(request: Request, fichiers: list[UploadFile],
               extractor=Depends(get_extractor)):
        # Chemin de repli sans JS : traite tout le lot d'un coup.
        recap = {"ingeree": 0, "ignoree": 0, "en_revue": 0, "erreur": 0}
        details = []
        cout_lot = 0.0
        for f in fichiers:
            r = _ingerer_un(f, extractor)
            recap[r["statut"]] = recap.get(r["statut"], 0) + 1
            details.append((r["fichier"], r["statut"], r["motif"], r["cout"]))
            cout_lot += r["cout"]
        return TEMPLATES.TemplateResponse(
            request, "import_labos.html",
            {"recap": recap, "details": details, "cout_lot": round(cout_lot, 4),
             "n_total": _nombre_factures(), "cout_total": _cout_total()})

    TAILLE_PAGE = 50

    @app.get("/referentiel", response_class=HTMLResponse)
    def referentiel(request: Request, q: str = "", page: int = 1):
        q = q.strip()
        where, params = "", []
        if q:
            like = f"%{q}%"
            where = ("WHERE code LIKE ? OR designation LIKE ? OR labo LIKE ? "
                     "OR date_facture LIKE ?")
            params = [like, like, like, like]
        c = conn()
        total = c.execute(
            f"SELECT COUNT(*) n FROM referentiel_prix {where}", params).fetchone()["n"]
        pages = max(1, (total + TAILLE_PAGE - 1) // TAILLE_PAGE)
        page = max(1, min(page, pages))
        rows = c.execute(
            "SELECT code, type_code, labo, date_facture, designation, prix_brut, "
            "remise_pct, prix_net, modifie_manuellement "
            f"FROM referentiel_prix {where} ORDER BY code, date_facture LIMIT ? OFFSET ?",
            params + [TAILLE_PAGE, (page - 1) * TAILLE_PAGE]).fetchall()
        return TEMPLATES.TemplateResponse(request, "referentiel.html", {
            "rows": rows, "q": q, "page": page, "pages": pages,
            "total": total, "taille": TAILLE_PAGE})

    @app.post("/referentiel/maj")
    def referentiel_maj(payload: dict):
        """Édition manuelle d'une ligne du référentiel (clé : code + date_facture).

        Seules les valeurs sont modifiables ; on recalcule le PA net pour rester
        cohérent et on marque la ligne pour qu'une ré-ingestion ne l'écrase pas.
        """
        code, date_facture = payload.get("code"), payload.get("date_facture")
        brut, remise, net = (payload.get("prix_brut"), payload.get("remise_pct"),
                             payload.get("prix_net"))
        # Cohérence : PA net recalculé depuis brut + remise s'il n'est pas forcé à la main.
        if net in (None, "") and brut not in (None, ""):
            taux = float(remise) if remise not in (None, "") else 0.0
            net = round(float(brut) * (1 - taux / 100), 4)
        c = conn()  # une seule connexion pour l'UPDATE + le commit
        cur = c.execute(
            "UPDATE referentiel_prix SET prix_brut=?, remise_pct=?, prix_net=?, "
            "modifie_manuellement=1 WHERE code=? AND date_facture=?",
            (brut, remise, net, code, date_facture))
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="ligne de référentiel introuvable")
        return {"prix_brut": brut, "remise_pct": remise, "prix_net": net,
                "modifie_manuellement": True}

    # Colonnes triables (clé d'URL -> colonne SQL). Liste blanche = pas d'injection.
    COLS_TRI_FACTURES = {
        "id": "id", "fichier": "fichier", "labo": "labo", "type": "type_document",
        "statut": "statut", "motif": "motif", "affiche": "total_affiche",
        "calcule": "total_calcule", "modele": "modele_extraction"}

    @app.get("/factures", response_class=HTMLResponse)
    def factures(request: Request, q: str = "", page: int = 1,
                 tri: str = "id", sens: str = "desc"):
        q = q.strip()
        where, params = "", []
        if q:
            like = f"%{q}%"
            where = ("WHERE fichier LIKE ? OR labo LIKE ? OR statut LIKE ? "
                     "OR motif LIKE ? OR date_facture LIKE ?")
            params = [like] * 5
        col = COLS_TRI_FACTURES.get(tri, "id")
        sens = "asc" if sens == "asc" else "desc"
        c = conn()
        total = c.execute(f"SELECT COUNT(*) n FROM factures {where}", params).fetchone()["n"]
        pages = max(1, (total + TAILLE_PAGE - 1) // TAILLE_PAGE)
        page = max(1, min(page, pages))
        rows = c.execute(
            "SELECT id, fichier, labo, type_document, statut, motif, total_affiche, "
            f"total_calcule, modele_extraction FROM factures {where} "
            f"ORDER BY {col} {sens.upper()}, id DESC LIMIT ? OFFSET ?",
            params + [TAILLE_PAGE, (page - 1) * TAILLE_PAGE]).fetchall()
        return TEMPLATES.TemplateResponse(request, "factures.html", {
            "rows": rows, "q": q, "page": page, "pages": pages, "total": total,
            "taille": TAILLE_PAGE, "tri": tri, "sens": sens})

    @app.get("/facture-labo/{fid}", response_class=HTMLResponse)
    def facture_labo(request: Request, fid: int):
        c = conn()
        f = c.execute(
            "SELECT id, fichier, labo, numero_facture, date_facture, type_document, "
            "statut, motif, total_affiche, total_calcule, modele_extraction "
            "FROM factures WHERE id=?", (fid,)).fetchone()
        if f is None:
            return RedirectResponse("/factures", status_code=303)
        lignes = c.execute(
            "SELECT code, type_code, code_interne, designation, qte, prix_net, "
            "montant_ht, checksum_ok, valide FROM lignes_facture "
            "WHERE facture_id=? ORDER BY id", (fid,)).fetchall()
        # Cohérence par ligne : qté×PA net ≈ montant HT -> repère la ligne fautive.
        details, somme = [], 0.0
        for l in lignes:
            mt = l["montant_ht"]
            attendu = (l["qte"] or 0) * (l["prix_net"] or 0)
            incoherent = mt is not None and abs(attendu - mt) > max(0.02, abs(mt) * 0.01)
            if mt is not None:
                somme += mt
            details.append({"l": l, "attendu": round(attendu, 2), "incoherent": incoherent})
        ta = f["total_affiche"]
        ecart = round(somme - ta, 2) if ta is not None else None
        return TEMPLATES.TemplateResponse(request, "facture_labo.html", {
            "f": f, "details": details, "somme": round(somme, 2), "ecart": ecart})

    @app.post("/facture-labo/{fid}/integrer")
    def integrer_facture_labo(fid: int):
        """Après vérification manuelle : pousse les lignes valides au référentiel."""
        c = conn()
        f = c.execute("SELECT id, labo, date_facture FROM factures WHERE id=?",
                      (fid,)).fetchone()
        if f is None:
            return RedirectResponse("/factures", status_code=303)
        lignes = c.execute(
            "SELECT code, code_interne, type_code, designation, prix_brut, remise_pct, "
            "prix_net, valide FROM lignes_facture WHERE facture_id=?", (fid,)).fetchall()
        entrees = []
        for row in lignes:
            code_ref = row["code"] or row["code_interne"]
            if not row["valide"] or not code_ref:
                continue
            lf = LigneFacture(designation=row["designation"] or "", prix_brut=row["prix_brut"],
                              remise_pct=row["remise_pct"], prix_net=row["prix_net"])
            entrees.append((code_ref, row["type_code"], lf))
        enregistrer_referentiel(c, fid, f["date_facture"], f["labo"], entrees)
        c.execute("UPDATE factures SET statut='ingeree', "
                  "motif='intégré au référentiel après vérification manuelle' WHERE id=?", (fid,))
        c.commit()
        return RedirectResponse(f"/facture-labo/{fid}?ok=1", status_code=303)

    @app.get("/export-base")
    def export_base():
        return FileResponse(app.state.db_path, filename="retrocession.db")

    @app.post("/import-base")
    def import_base(fichier: UploadFile):
        Path(app.state.db_path).write_bytes(fichier.file.read())
        return RedirectResponse("/factures", status_code=303)

    def _nombre_retro():
        return conn().execute("SELECT COUNT(*) n FROM retro_documents").fetchone()["n"]

    def _nombre_referentiel():
        return conn().execute("SELECT COUNT(*) n FROM referentiel_prix").fetchone()["n"]

    def _cout_total_retro():
        v = conn().execute(
            "SELECT COALESCE(SUM(cout_estime), 0) c FROM retro_documents").fetchone()["c"]
        return round(max(0.0, v - float(_param("cout_baseline_retro", "0"))), 4)

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
                   "erreur": _motif_erreur(e)}
        finally:
            Path(chemin).unlink(missing_ok=True)
        out.update({"fichier": fichier.filename,
                    "n_total": _nombre_retro(), "cout_total": _cout_total_retro()})
        return out

    @app.get("/retro", response_class=HTMLResponse)
    def retro(request: Request):
        return TEMPLATES.TemplateResponse(
            request, "retro.html",
            {"n_total": _nombre_retro(), "cout_total": _cout_total_retro(),
             "n_referentiel": _nombre_referentiel()})

    @app.post("/retro/ingest-un")
    def retro_ingest_un(fichier: UploadFile, extractor=Depends(get_retro_extractor)):
        return _ingerer_retro_un(fichier, extractor)

    @app.get("/retro-lignes", response_class=HTMLResponse)
    def retro_lignes(request: Request, q: str = "", periode: str = "", page: int = 1):
        q = q.strip()
        conds, params = [], []
        if q:
            like = f"%{q}%"
            conds.append("(d.numero LIKE ? OR l.designation LIKE ? OR l.code LIKE ? "
                         "OR l.bl_numero LIKE ? OR l.bl_date LIKE ? OR l.statut_ecart LIKE ?)")
            params += [like] * 6
        if len(periode) == 7:
            conds.append("l.bl_date LIKE ?")
            params.append(f"%/{periode[5:7]}/{periode[:4]}")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        c = conn()
        total = c.execute(
            "SELECT COUNT(*) n FROM retro_lignes l "
            f"JOIN retro_documents d ON d.id = l.retro_id {where}", params).fetchone()["n"]
        pages = max(1, (total + TAILLE_PAGE - 1) // TAILLE_PAGE)
        page = max(1, min(page, pages))
        rows = c.execute(
            "SELECT d.numero, l.bl_numero, l.bl_date, l.designation, l.code, l.qte, "
            "l.tva, l.prix_net, l.statut_ecart "
            f"FROM retro_lignes l JOIN retro_documents d ON d.id = l.retro_id {where} "
            "ORDER BY l.id LIMIT ? OFFSET ?",
            params + [TAILLE_PAGE, (page - 1) * TAILLE_PAGE]).fetchall()
        return TEMPLATES.TemplateResponse(request, "retro_lignes.html", {
            "rows": rows, "q": q, "periode": periode,
            "mois": _mois_disponibles(c, "retro_lignes", "bl_date"),
            "page": page, "pages": pages, "total": total, "taille": TAILLE_PAGE})

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
            out = {"statut": "erreur", "motif": _motif_erreur(e),
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
            out = {"statut": "erreur", "motif": _motif_erreur(e),
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

    def _facture_ou_404(retro_id):
        f = construire_facture(conn(), retro_id)
        if f is None:
            raise HTTPException(status_code=404, detail="facture introuvable")
        return f

    @app.get("/factures-retro", response_class=HTMLResponse)
    def factures_retro(request: Request, q: str = "", periode: str = "", page: int = 1):
        q = q.strip()
        conds, params = [], []
        if q:
            like = f"%{q}%"
            conds.append("(d.numero LIKE ? OR d.pharmacie_emettrice LIKE ? "
                         "OR d.pharmacie_destinataire LIKE ? OR d.date_vente LIKE ?)")
            params += [like] * 4
        if len(periode) == 7:                     # 'AAAA-MM' -> dates JJ/MM/AAAA
            conds.append("d.date_vente LIKE ?")
            params.append(f"%/{periode[5:7]}/{periode[:4]}")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        c = conn()
        total = c.execute(
            f"SELECT COUNT(*) n FROM retro_documents d {where}", params).fetchone()["n"]
        pages = max(1, (total + TAILLE_PAGE - 1) // TAILLE_PAGE)
        page = max(1, min(page, pages))
        rows = c.execute(
            "SELECT d.id, d.numero, d.pharmacie_emettrice, d.pharmacie_destinataire, "
            "d.reconciliation_ok, COUNT(l.id) n_lignes, "
            "SUM(CASE WHEN l.statut_ecart='rouge' THEN 1 ELSE 0 END) n_rouge, "
            "(SELECT COUNT(*) FROM retro_documents d2 WHERE d2.numero = d.numero "
            " AND d.numero IS NOT NULL) AS n_meme_numero "
            f"FROM retro_documents d LEFT JOIN retro_lignes l ON l.retro_id = d.id {where} "
            "GROUP BY d.id ORDER BY d.id DESC LIMIT ? OFFSET ?",
            params + [TAILLE_PAGE, (page - 1) * TAILLE_PAGE]).fetchall()
        return TEMPLATES.TemplateResponse(request, "factures_retro.html", {
            "rows": rows, "q": q, "periode": periode,
            "mois": _mois_disponibles(c, "retro_documents", "date_vente"),
            "page": page, "pages": pages, "total": total, "taille": TAILLE_PAGE})

    @app.get("/facture/{retro_id}", response_class=HTMLResponse)
    def facture(request: Request, retro_id: int):
        f = _facture_ou_404(retro_id)
        return TEMPLATES.TemplateResponse(request, "facture.html", {"f": f})

    @app.post("/facture/{retro_id}/recalculer")
    def facture_recalculer(retro_id: int):
        """Propage le référentiel à cette facture (lignes auto-rapprochées uniquement)."""
        return recalculer_prix_facture(conn(), retro_id)

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

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon_ico():
        return FileResponse("app/ui/static/retrobuddy.ico")

    @app.get("/favicon.png", include_in_schema=False)
    def favicon_png():
        return FileResponse("app/ui/static/favicon.png")

    @app.get("/mascotte.png", include_in_schema=False)
    def mascotte():
        return FileResponse("app/ui/static/mascotte.png")

    # ---- Réglages : clé API, coûts, suppression de données ----

    def _compteurs_donnees():
        c = conn()
        n = lambda t: c.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
        return {"referentiel": n("referentiel_prix"), "factures": n("factures"),
                "lignes_facture": n("lignes_facture"), "retro": n("retro_documents"),
                "retro_lignes": n("retro_lignes")}

    @app.get("/reglages", response_class=HTMLResponse)
    def reglages(request: Request):
        cle_presente, cle_masquee = _cle_info()
        return TEMPLATES.TemplateResponse(request, "reglages.html", {
            "cle_presente": cle_presente, "cle_masquee": cle_masquee,
            "compteurs": _compteurs_donnees(),
            "cout_labo": _cout_total(), "cout_retro": _cout_total_retro()})

    @app.post("/config/cle")
    def config_cle(cle: str = Form(...), retour: str = Form("/reglages")):
        cle = cle.strip()
        sep = "&" if "?" in retour else "?"
        if not cle.startswith("sk-ant-"):           # validation format, clé jamais loggée
            return RedirectResponse(retour + sep + "err=cle", status_code=303)
        enregistrer_cle_api(cle)
        return RedirectResponse(retour + sep + "ok=cle", status_code=303)

    @app.post("/cout/reset/{quoi}")
    def cout_reset(quoi: str):
        # Baseline non-destructif : on mémorise le cumul courant comme "point zéro".
        if quoi in ("labo", "tout"):
            v = conn().execute("SELECT COALESCE(SUM(cout_estime),0) c FROM factures").fetchone()["c"]
            _set_param("cout_baseline_labo", v)
        if quoi in ("retro", "tout"):
            v = conn().execute("SELECT COALESCE(SUM(cout_estime),0) c FROM retro_documents").fetchone()["c"]
            _set_param("cout_baseline_retro", v)
        return RedirectResponse("/reglages?ok=cout-" + quoi, status_code=303)

    @app.post("/donnees/supprimer/{quoi}")
    def donnees_supprimer(quoi: str, confirmation: str = Form(...)):
        if confirmation.strip().upper() != "SUPPRIMER":
            return RedirectResponse("/reglages?err=confirmation", status_code=303)
        tables = {
            "referentiel": ["referentiel_prix"],
            "factures": ["lignes_facture", "factures"],
            "retro": ["retro_lignes", "retro_documents"],
            "tout": ["lignes_facture", "factures", "referentiel_prix",
                     "retro_lignes", "retro_documents", "correspondance_codes"],
        }
        if quoi not in tables:
            raise HTTPException(status_code=404, detail="catégorie inconnue")
        c = conn()
        for t in tables[quoi]:
            c.execute(f"DELETE FROM {t}")
        if quoi in ("factures", "tout"):           # données effacées -> baseline coût remise à 0
            c.execute("INSERT INTO parametres(cle,valeur) VALUES('cout_baseline_labo','0') "
                      "ON CONFLICT(cle) DO UPDATE SET valeur='0'")
        if quoi in ("retro", "tout"):
            c.execute("INSERT INTO parametres(cle,valeur) VALUES('cout_baseline_retro','0') "
                      "ON CONFLICT(cle) DO UPDATE SET valeur='0'")
        c.commit()
        return RedirectResponse("/reglages?ok=suppr-" + quoi, status_code=303)

    return app


app = creer_app()
