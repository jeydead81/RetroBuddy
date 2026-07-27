from app.surveillance import est_surveille


def test_est_surveille_designation_ou_code():
    termes = ["biogaran", "3401"]
    assert est_surveille("DOLIPRANE BIOGARAN 500", None, termes) is True    # labo dans désignation
    assert est_surveille("X", "3401234567890", termes) is True              # code
    assert est_surveille("DOLIPRANE", "9999999999999", termes) is False
    assert est_surveille("X", None, []) is False                            # aucune surveillance
