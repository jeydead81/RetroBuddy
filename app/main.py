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
