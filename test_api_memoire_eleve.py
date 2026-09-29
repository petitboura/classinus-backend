"""
Test manuel des routes de l'ecran "Ma memoire" (api/memoire_eleve.py),
meme convention que test_outils_memoire_eleve.py : vraie application
FastAPI et vraie requete HTTP (TestClient), seule la couche Supabase est
remplacee par une base simulee qui enregistre les appels recus.

Couvre : lecture groupee par categorie (4 categories toujours presentes,
ligne racine en premier), effacement d'une categorie, effacement total,
categorie inconnue, pannes de la base (code d'erreur stable, jamais de
500 brut).
"""

import logging
import os
import sys
from unittest.mock import patch

os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault(
    "SUPABASE_SECRET",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x",
)
sys.path.append("core")
logging.disable(logging.CRITICAL)

from fastapi.testclient import TestClient  # noqa: E402

import api.main as principal  # noqa: E402
import api.memoire_eleve as route  # noqa: E402
from api.auth import utilisateur_courant  # noqa: E402


class _Reponse:
    def __init__(self, data):
        self.data = data


class BaseSimulee:
    """Enregistre la chaine d'appels (select/delete + filtres eq) de chaque requete."""

    def __init__(self, lignes=None, panne=False):
        self.lignes = lignes or []
        self.panne = panne
        self.requetes = []
        self._courante = None

    def table(self, nom):
        self._courante = {"table": nom, "operation": None, "filtres": {}}
        self.requetes.append(self._courante)
        return self

    def select(self, colonnes):
        self._courante["operation"] = "select"
        return self

    def delete(self):
        self._courante["operation"] = "delete"
        return self

    def eq(self, colonne, valeur):
        self._courante["filtres"][colonne] = valeur
        return self

    def execute(self):
        if self.panne:
            raise RuntimeError("panne simulee")
        return _Reponse(self.lignes if self._courante["operation"] == "select" else [])


class Utilisateur:
    id = "eleve-1"


principal.app.dependency_overrides[utilisateur_courant] = lambda: Utilisateur()
client = TestClient(principal.app, raise_server_exceptions=False)


def avec_base(base):
    return patch.object(route, "supabase", base)


def verifier(condition, message):
    assert condition, f"ECHEC : {message}"
    print(f"OK : {message}")


# 1. Lecture groupee
base = BaseSimulee(lignes=[
    {"categorie": "apprentissage", "sous_categorie": "maths", "contenu": {"niveau": "solide"}, "description": "Maths", "updated_at": "2026-09-29T10:00:00+00:00"},
    {"categorie": "apprentissage", "sous_categorie": "", "contenu": {"point_faible": "anglais"}, "description": "Point faible", "updated_at": "2026-09-29T09:00:00+00:00"},
    {"categorie": "identite", "sous_categorie": "", "contenu": {"nom": "Boumi"}, "description": "Nom", "updated_at": "2026-09-29T08:00:00+00:00"},
    {"categorie": "categorie_inventee", "sous_categorie": "", "contenu": {}, "description": "intrus", "updated_at": ""},
])
with avec_base(base):
    r = client.get("/api/memoire-eleve")
verifier(r.status_code == 200, "GET : 200 pour un eleve connecte")
noms = [c["categorie"] for c in r.json()["categories"]]
verifier(noms == ["identite", "scolarite", "apprentissage", "preferences"], "GET : les 4 categories du socle, dans l'ordre, sans categorie inventee")
par_nom = {c["categorie"]: c["lignes"] for c in r.json()["categories"]}
verifier(par_nom["scolarite"] == [] and par_nom["preferences"] == [], "GET : categories vides renvoyees avec une liste vide, pas d'erreur")
verifier([l["sous_categorie"] for l in par_nom["apprentissage"]] == [None, "maths"], "GET : ligne racine (None) en premier puis sous-categories")
verifier(base.requetes[0]["filtres"] == {"user_id": "eleve-1"}, "GET : lecture filtree sur l'eleve connecte uniquement")

# 2. Lecture en panne
with avec_base(BaseSimulee(panne=True)):
    r = client.get("/api/memoire-eleve")
verifier(r.status_code == 500 and r.json()["detail"]["code"] == "MEMOIRE_ELEVE_LECTURE_ECHEC", "GET : panne base -> 500 avec code stable")

# 3. Effacement d'une categorie
base = BaseSimulee()
with avec_base(base):
    r = client.delete("/api/memoire-eleve/apprentissage")
verifier(r.status_code == 204, "DELETE categorie : 204")
verifier(base.requetes[0]["operation"] == "delete" and base.requetes[0]["filtres"] == {"user_id": "eleve-1", "categorie": "apprentissage"}, "DELETE categorie : filtre sur l'eleve ET la categorie, jamais les autres")

# 4. Categorie inconnue : refusee avant tout appel a la base
base = BaseSimulee()
with avec_base(base):
    r = client.delete("/api/memoire-eleve/inventee")
verifier(r.status_code == 404 and r.json()["detail"]["code"] == "MEMOIRE_ELEVE_CATEGORIE_INCONNUE", "DELETE categorie inconnue : 404 avec code stable")
verifier(base.requetes == [], "DELETE categorie inconnue : aucun appel a la base")

# 5. Effacement total
base = BaseSimulee()
with avec_base(base):
    r = client.delete("/api/memoire-eleve")
verifier(r.status_code == 204, "DELETE tout : 204")
verifier(base.requetes[0]["filtres"] == {"user_id": "eleve-1"}, "DELETE tout : filtre sur l'eleve seul, aucune autre personne touchee")

# 6. Effacement en panne
with avec_base(BaseSimulee(panne=True)):
    r1 = client.delete("/api/memoire-eleve/identite")
    r2 = client.delete("/api/memoire-eleve")
verifier(
    r1.status_code == 500 and r2.status_code == 500
    and r1.json()["detail"]["code"] == r2.json()["detail"]["code"] == "MEMOIRE_ELEVE_EFFACEMENT_ECHEC",
    "DELETE : panne base -> 500 avec code stable, sur les deux routes",
)

# 7. Les codes d'erreur ont un message francais (sinon message generique)
from core.erreurs import MESSAGES_FR  # noqa: E402
for code in ("MEMOIRE_ELEVE_LECTURE_ECHEC", "MEMOIRE_ELEVE_EFFACEMENT_ECHEC", "MEMOIRE_ELEVE_CATEGORIE_INCONNUE"):
    verifier(code in MESSAGES_FR, f"code {code} declare dans MESSAGES_FR")

principal.app.dependency_overrides.clear()
print("\nTous les cas passent (routes de l'ecran Ma memoire).")
