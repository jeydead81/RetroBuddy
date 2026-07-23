import threading

from app.db import get_connection, init_db


def test_connexion_wal_et_busy_timeout(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000


def test_ecriture_pendant_lecture_ouverte(tmp_path):
    # Reproduit la config du bug « Re-rapprocher » : une connexion garde une lecture
    # ouverte pendant qu'une autre écrit. En WAL, l'écriture doit passer.
    db = tmp_path / "t.db"
    c = get_connection(db)
    init_db(c)
    c.execute("INSERT INTO retro_documents (id, fichier) VALUES (1, 'r.pdf')")
    c.execute("INSERT INTO retro_lignes (retro_id, designation) VALUES (1, 'X')")
    c.commit()

    lecteur = get_connection(db)
    lecteur.execute("BEGIN")
    lecteur.execute("SELECT * FROM retro_lignes").fetchone()   # lecture en cours

    ecrivain = get_connection(db)
    ecrivain.execute("UPDATE retro_lignes SET statut_ecart='resolu' WHERE retro_id=1")
    ecrivain.commit()                                          # ne doit PAS lever
    assert c.execute("SELECT statut_ecart FROM retro_lignes").fetchone()["statut_ecart"] == "resolu"


def test_ecritures_concurrentes_deux_threads(tmp_path):
    db = tmp_path / "t.db"
    init_db(get_connection(db))
    erreurs = []

    def writer(n):
        try:
            cx = get_connection(db)
            for i in range(50):
                cx.execute("INSERT INTO parametres (cle, valeur) VALUES (?, ?)",
                           (f"{n}-{i}", "x"))
                cx.commit()
        except Exception as e:  # noqa: BLE001
            erreurs.append(str(e))

    ts = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert erreurs == []
    n = get_connection(db).execute("SELECT COUNT(*) n FROM parametres").fetchone()["n"]
    assert n == 200
