from datetime import datetime, timezone


def fmt_qte(v):
    """Quantité sans décimale superflue (produits indivisibles) : 3.0 -> '3'.

    Conserve une éventuelle fraction réelle (2.5 -> '2.5'), gère None -> ''.
    """
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def fmt_horodatage(ts):
    """Horodatage SQLite (UTC, 'AAAA-MM-JJ HH:MM:SS') -> 'jj/mm/aa : hh:mm'
    en heure locale du poste (Paris, changement d'heure géré par l'OS).

    astimezone() sans argument utilise le fuseau système : aucune dépendance
    tzdata requise sous Windows. None ou format inattendu -> chaîne brute/vide.
    """
    if not ts:
        return ""
    brut = str(ts)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(brut, fmt).replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime("%d/%m/%y : %H:%M")
        except ValueError:
            continue
    return brut
