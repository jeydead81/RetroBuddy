import re

from app.format_util import fmt_horodatage


def test_horodatage_format_jj_mm_aa_hh_mm():
    # Peu importe le fuseau du poste : la forme doit être 'jj/mm/aa : hh:mm'.
    out = fmt_horodatage("2026-08-10 12:00:00")
    assert re.fullmatch(r"\d{2}/\d{2}/\d{2} : \d{2}:\d{2}", out), out


def test_horodatage_accepte_les_variantes_iso():
    assert re.fullmatch(r"\d{2}/\d{2}/\d{2} : \d{2}:\d{2}",
                        fmt_horodatage("2026-08-10T12:00:00"))
    assert re.fullmatch(r"\d{2}/\d{2}/\d{2} : \d{2}:\d{2}",
                        fmt_horodatage("2026-08-10 12:00:00.123456"))


def test_horodatage_vide_ou_invalide():
    assert fmt_horodatage(None) == ""
    assert fmt_horodatage("") == ""
    assert fmt_horodatage("pas une date") == "pas une date"
