import threading
import uuid


class RegistreJobs:
    """Registre en mémoire des jobs d'ingestion (app mono-processus local)."""

    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def creer(self, total):
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {"total": total, "fait": 0, "cout": 0.0,
                                  "details": [], "termine": False}
        return job_id

    def ajouter(self, job_id, resultat):
        with self._lock:
            j = self._jobs.get(job_id)
            if j is not None:
                j["fait"] += 1
                j["cout"] = round(j["cout"] + float(resultat.get("cout", 0.0)), 5)
                j["details"].append(resultat)

    def terminer(self, job_id):
        with self._lock:
            j = self._jobs.get(job_id)
            if j is not None:
                j["termine"] = True

    def lire(self, job_id):
        with self._lock:
            j = self._jobs.get(job_id)
            return {"total": j["total"], "fait": j["fait"], "cout": j["cout"],
                    "details": list(j["details"]), "termine": j["termine"]} if j else None


def lancer_job(registre, job_id, fichiers, traiter_un):
    """Démarre un thread qui traite chaque (nom, chemin) via traiter_un(nom, chemin) -> dict.

    Un fichier qui échoue n'interrompt pas le lot. Retourne le thread (pour join en test).
    """
    def _run():
        for nom, chemin in fichiers:
            try:
                r = traiter_un(nom, chemin)
            except Exception as e:
                r = {"fichier": nom, "statut": "erreur", "motif": str(e), "cout": 0.0}
            registre.ajouter(job_id, r)
        registre.terminer(job_id)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
