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
    # Colle un nombre immédiatement suivi d'une unité (ex: "1000 MG" -> "1000MG")
    t = re.sub(r"(\d+) ([A-Z]+)(?= |$)", r"\1\2", t)
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
