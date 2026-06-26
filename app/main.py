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
from app.temps2.schemas import RetroExtrait
from app.temps2.traitement_retro import traiter_retro
from app.temps3 import resolution as resolution_logique
from app.temps3.rematch import rematcher
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


def creer_app(db_path="data/retrocession.db") -> FastAPI:
    app = FastAPI(title="RetroBuddy")
    app.state.db_path = db_path
    app.state.config = charger_config()
    app.state.jobs = RegistreJobs()
    app.state.jobs_retro = RegistreJobs()

    init_db(get_connection(db_path))

    def conn():
        return get_connection(app.state.db_path)

    def _nombre_factures():
        return conn().execute("SELECT COUNT(*) n FROM factures").fetchone()["n"]

    def _cout_total():
        v = conn().execute(
            "SELECT COALESCE(SUM(cout_estime), 0) c FROM factures").fetchone()["c"]
        return round(v, 4)

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
            statut, motif, n_ref, cout = "erreur", f"extraction impossible : {e}", 0, 0.0
        finally:
            Path(chemin).unlink(missing_ok=True)
        return {"fichier": fichier.filename, "statut": statut, "motif": motif,
                "n_referentiel": n_ref, "cout": round(cout, 5),
                "n_total": _nombre_factures(), "cout_total": _cout_total()}

    @app.get("/", response_class=HTMLResponse)
    def accueil(request: Request):
        return TEMPLATES.TemplateResponse(
            request, "accueil.html",
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
            request, "accueil.html",
            {"recap": recap, "details": details, "cout_lot": round(cout_lot, 4),
             "n_total": _nombre_factures(), "cout_total": _cout_total()})

    @app.get("/referentiel", response_class=HTMLResponse)
    def referentiel(request: Request):
        rows = conn().execute(
            "SELECT code, type_code, labo, date_facture, designation, "
            "prix_brut, remise_pct, prix_net "
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

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon_ico():
        return FileResponse("app/ui/static/retrobuddy.ico")

    @app.get("/favicon.png", include_in_schema=False)
    def favicon_png():
        return FileResponse("app/ui/static/favicon.png")

    return app


app = creer_app()
