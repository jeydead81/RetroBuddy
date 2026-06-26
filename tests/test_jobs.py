from app.jobs import RegistreJobs, lancer_job


def test_job_traite_tous_les_fichiers():
    reg = RegistreJobs()
    jid = reg.creer(2)
    appels = []

    def traiter_un(nom, chemin):
        appels.append(nom)
        return {"fichier": nom, "statut": "ok", "cout": 0.01}

    t = lancer_job(reg, jid, [("a.pdf", "/tmp/a"), ("b.pdf", "/tmp/b")], traiter_un)
    t.join(timeout=5)
    j = reg.lire(jid)
    assert j["termine"] is True
    assert j["fait"] == 2
    assert round(j["cout"], 2) == 0.02
    assert len(j["details"]) == 2
    assert appels == ["a.pdf", "b.pdf"]


def test_job_inconnu_renvoie_none():
    assert RegistreJobs().lire("zzz") is None


def test_job_continue_malgre_une_erreur():
    reg = RegistreJobs()
    jid = reg.creer(2)

    def traiter_un(nom, chemin):
        if nom == "boom.pdf":
            raise RuntimeError("boom")
        return {"fichier": nom, "statut": "ok", "cout": 0.0}

    t = lancer_job(reg, jid, [("boom.pdf", "/tmp/x"), ("ok.pdf", "/tmp/y")], traiter_un)
    t.join(timeout=5)
    j = reg.lire(jid)
    assert j["fait"] == 2
    assert j["details"][0]["statut"] == "erreur"
    assert j["details"][1]["statut"] == "ok"
