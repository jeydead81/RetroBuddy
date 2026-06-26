import datetime

from app.temps2.normalisation_dates import normaliser_date


def test_jj_mm_aaaa():
    assert normaliser_date("01/08/2025") == datetime.date(2025, 8, 1)


def test_jj_point_mm_point_aaaa():
    assert normaliser_date("02.03.2026") == datetime.date(2026, 3, 2)


def test_iso():
    assert normaliser_date("2026-03-02") == datetime.date(2026, 3, 2)


def test_annee_2_chiffres():
    assert normaliser_date("31/08/25") == datetime.date(2025, 8, 31)


def test_illisible_renvoie_none():
    assert normaliser_date("le 3 mars") is None


def test_none_renvoie_none():
    assert normaliser_date(None) is None
