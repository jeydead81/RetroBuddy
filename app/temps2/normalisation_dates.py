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
