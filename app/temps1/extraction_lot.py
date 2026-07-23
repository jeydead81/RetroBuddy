"""Extraction par lots via la Batch API Anthropic : mêmes modèles, mêmes prompts,
mêmes sorties structurées que l'extraction unitaire, facturées **moitié prix**.
Seule différence : les résultats arrivent en différé (minutes, < 1 h en général).

Tenue en charge (imports de plusieurs milliers de PDF) :
- découpage en sous-lots sous les limites API (256 Mo / 100 000 requêtes par lot) ;
- les PDF sont lus depuis le disque sous-lot par sous-lot (jamais tout en mémoire) ;
- les résultats sont consommés en flux (un par un), pas accumulés.
"""

import base64
import time

from anthropic.lib._parse._transform import transform_schema

from app.temps1.cout import cout_appel
from app.temps1.extraction_ia import MAX_TOKENS_EXTRACTION, ExtractionError

REMISE_LOT = 0.5                                # la Batch API est facturée -50 %
MAX_OCTETS_SOUS_LOT = 50 * 1024 * 1024          # marge large sous les 256 Mo/lot de l'API
MAX_REQUETES_SOUS_LOT = 1000                    # et sous les 100 000 requêtes/lot
_DELAI_MAX_S = 26 * 3600                        # l'API garantit < 24 h ; au-delà on abandonne


class EscaladeDifferee(Exception):
    """Le pipeline réclame le modèle d'escalade : à re-traiter dans un 2e lot."""


class ExtracteurPreExtrait:
    """Extracteur compatible pipeline dont les extractions ont déjà eu lieu (en lot).

    par_modele : {modele: (resultat_pydantic, cout_eur)}. Un modèle absent lève
    EscaladeDifferee — l'appelant met le fichier de côté pour le lot suivant.
    """

    def __init__(self, par_modele):
        self._par_modele = par_modele
        self.dernier_cout = 0.0

    def extraire(self, pdf, model):
        if model not in self._par_modele:
            raise EscaladeDifferee(model)
        resultat, cout = self._par_modele[model]
        self.dernier_cout = cout
        return resultat


def _params_requete(modele, prompt, schema, pdf_b64):
    # Miroir exact de ClaudeExtractor.extraire (messages.parse), en forme "batch".
    return {
        "model": modele,
        "max_tokens": MAX_TOKENS_EXTRACTION,
        "system": [{"type": "text", "text": prompt,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf",
                            "data": pdf_b64}},
                {"type": "text", "text": "Extrais cette facture selon le schéma."},
            ],
        }],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }


def soumettre_lots(client, modele, prompt, output_format, fichiers):
    """Soumet les fichiers en un ou plusieurs sous-lots. Retourne les ids de lots.

    fichiers : liste de (cle, chemin) — la clé (custom_id) doit être unique.
    Les PDF sont lus au moment de construire chaque sous-lot puis libérés.
    """
    schema = transform_schema(output_format.model_json_schema())
    lots, requetes, octets = [], [], 0
    createur = client.with_options(timeout=900.0) if hasattr(client, "with_options") else client

    def _envoyer():
        nonlocal requetes, octets
        if requetes:
            lot = createur.messages.batches.create(requests=requetes)
            lots.append(lot.id)
            requetes, octets = [], 0

    for cle, chemin in fichiers:
        with open(chemin, "rb") as f:
            b64 = base64.standard_b64encode(f.read()).decode("ascii")
        if requetes and (octets + len(b64) > MAX_OCTETS_SOUS_LOT
                         or len(requetes) >= MAX_REQUETES_SOUS_LOT):
            _envoyer()
        requetes.append({"custom_id": str(cle),
                         "params": _params_requete(modele, prompt, schema, b64)})
        octets += len(b64)
    _envoyer()
    return lots


def attendre_lots(client, lots, progression=None, intervalle=15):
    """Attend la fin de tous les lots ; `progression(n_terminees)` à chaque point."""
    debut = time.monotonic()
    en_cours = list(lots)
    while True:
        faits = 0
        restants = []
        for lot_id in en_cours:
            b = client.messages.batches.retrieve(lot_id)
            c = b.request_counts
            faits += c.succeeded + c.errored + c.canceled + c.expired
            if b.processing_status != "ended":
                restants.append(lot_id)
        if progression:
            progression(faits)
        if not restants:
            return
        # les lots terminés ne bougent plus : on compte large en les re-comptant
        if time.monotonic() - debut > _DELAI_MAX_S:
            raise ExtractionError("lot d'extraction non terminé après 26 h — réessayez")
        time.sleep(intervalle)


def resultats_lots(client, lots, modele, output_format):
    """Itère (cle, ok, resultat_ou_motif, cout_eur) au fil de l'eau (jamais tout en RAM)."""
    for lot_id in lots:
        for r in client.messages.batches.results(lot_id):
            cle = r.custom_id
            if r.result.type != "succeeded":
                motif = "erreur API sur ce fichier (lot)"
                if r.result.type == "errored":
                    motif = f"erreur API sur ce fichier : {getattr(r.result.error, 'type', '?')}"
                yield cle, False, motif, 0.0
                continue
            msg = r.result.message
            cout = cout_appel(modele, msg.usage) * REMISE_LOT
            if msg.stop_reason == "refusal":
                yield cle, False, "extraction refusée par le modèle", cout
                continue
            if msg.stop_reason == "max_tokens":
                yield cle, False, ("réponse tronquée : facture trop longue pour une "
                                   "extraction en un appel"), cout
                continue
            texte = next((b.text for b in msg.content if b.type == "text"), None)
            if not texte:
                yield cle, False, "réponse sans contenu exploitable", cout
                continue
            try:
                yield cle, True, output_format.model_validate_json(texte), cout
            except Exception:
                yield cle, False, "extraction non conforme au schéma", cout
