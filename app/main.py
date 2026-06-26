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

    return app


app = creer_app()
