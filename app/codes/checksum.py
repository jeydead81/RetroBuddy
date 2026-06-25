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


def type_de_code(code) -> str:
    if not code:
        return "inconnu"
    c = str(code).strip()
    if not c.isdigit():
        return "interne"
    if len(c) != 13:
        return "interne"   # codes internes courts
    if cip13_valide(c):
        return "CIP13"
    if ean13_valide(c):
        return "EAN13"
    return "inconnu"        # 13 chiffres mais clé KO → suspect
