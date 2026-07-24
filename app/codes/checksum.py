def _cle_gtin13(douze_chiffres: str) -> int:
    total = 0
    for i, ch in enumerate(douze_chiffres):
        n = int(ch)
        total += n if i % 2 == 0 else n * 3
    return (10 - (total % 10)) % 10


def _gtin13_valide(code) -> bool:
    if not code or len(str(code)) != 13 or not str(code).isdigit():
        return False
    code = str(code)
    return _cle_gtin13(code[:12]) == int(code[12])


def ean13_valide(code) -> bool:
    return _gtin13_valide(code)


def cip13_valide(code) -> bool:
    return _gtin13_valide(code) and str(code).startswith("34009")


def normaliser_code(code) -> str:
    """Nettoie un code produit : espaces retirés ; un GTIN-14 à zéro de tête
    (0 suivi d'un EAN13, forme fréquente sur les factures labo comme Bayer) est
    ramené à ses 13 chiffres. Un code interne court est renvoyé tel quel."""
    if code is None:
        return ""
    c = "".join(str(code).split())
    if len(c) == 14 and c.isdigit() and c.startswith("0"):
        c = c[1:]
    return c


def type_de_code(code) -> str:
    c = normaliser_code(code)
    if not c:
        return "inconnu"
    if not c.isdigit():
        return "interne"
    if len(c) != 13:
        return "interne"   # codes internes courts
    if cip13_valide(c):
        return "CIP13"
    if ean13_valide(c):
        return "EAN13"
    return "inconnu"        # 13 chiffres mais clé KO → suspect
