"""
Vérifie que l'appel MCP d'une question bloquante n'est PAS coupé par le délai général des outils
(60 s par défaut, voir core/mcp_tools.py::appeler_outil), et que l'identifiant de l'appel est
bien donné à l'outil (core/execution_outils.py::_executer_un_appel).

Même méthode que tests/verifier_delai_outils.py : on extrait les fonctions du fichier, sans
importer tout le serveur.

Lancer : python3 tests/verifier_delai_question_outil.py
"""
import ast
import asyncio
import json
import logging
import os
import sys
import time
import types

RACINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RACINE)
from core import questions_utilisateur as q  # noqa: E402

echecs = []


def verifier(nom, condition, detail=""):
    print(("OK   " if condition else "ECHEC"), nom, detail)
    if not condition:
        echecs.append(nom)


def extraire(chemin, noms):
    source = open(os.path.join(RACINE, chemin), encoding="utf-8").read()
    noeuds = []
    for n in ast.parse(source).body:
        nom = getattr(n, "name", None) or (n.targets[0].id if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) else None)
        if nom in noms:
            noeuds.append(n)
    return ast.Module(body=noeuds, type_ignores=[])


# Réglage du délai : 2 secondes, pour tester vite (le code ajoute la marge de l'appel)
faux_mcp = types.ModuleType("core.mcp_tools")
faux_mcp.parametres_outils = lambda: {q.CLE_DELAI_QUESTION: 30}
sys.modules["core.mcp_tools"] = faux_mcp
q.DELAI_QUESTION_MIN_SECONDES = 1
faux_mcp.parametres_outils = lambda: {q.CLE_DELAI_QUESTION: 2}

etat = {"duree": 0.1, "args": None}


async def faux_serveur(url, nom, arguments, headers=None):
    etat["args"] = dict(arguments)
    await asyncio.sleep(etat["duree"])
    return "ok"


ns = {
    "asyncio": asyncio, "logging": logging, "os": os, "time": time,
    "NOM_OUTIL_QUESTION": q.NOM_OUTIL_QUESTION,
    "MARGE_APPEL_QUESTION_SECONDES": 1,  # marge réduite pour le test
    "delai_question_secondes": q.delai_question_secondes,
    "est_bloquante": q.est_bloquante,
    "PARAMETRE_LIBELLE_OUTIL": "libelle_outil",
    "_appeler_outil_async": faux_serveur,
    "_message_erreur_technique_outil": lambda n: "erreur technique",
    "_reveiller_si_recent_non_tente": lambda url: None,
}
exec(compile(extraire("core/mcp_tools.py", {
    "_entier_env", "DELAI_OUTIL_DEFAUT_SECONDES", "DELAI_OUTIL_MAX_SECONDES", "PARAMETRE_DELAI_OUTIL",
    "_AppelAnnule", "_delai_demande", "_appeler_avec_delai_et_arret", "appeler_outil",
}), "mcp_tools_extrait", "exec"), ns)
ns["DELAI_OUTIL_DEFAUT_SECONDES"] = 1  # délai général de 1 s au lieu de 60 s
ns["DELAI_OUTIL_MAX_SECONDES"] = 1
appeler = ns["appeler_outil"]
table = {"poser_question": {"url": "u"}, "autre_outil": {"url": "u"}}

etat["duree"] = 1.5  # plus long que le délai général (1 s), plus court que le délai de la question (2 s + marge)
resultat = appeler("autre_outil", {}, table)
verifier("1 un outil ordinaire est coupé au délai général", "Délai dépassé" in resultat, resultat[:40])
resultat = appeler("poser_question", {"question": "{}", "bloquante": False}, table)
verifier("2 une question NON bloquante garde le délai général", "Délai dépassé" in resultat, resultat[:40])
resultat = appeler("poser_question", {"question": "{}", "bloquante": True, "id_question": "c1"}, table)
verifier("3 une question bloquante attend au delà du délai général", resultat == "ok", resultat[:40])
verifier("4 l'identifiant de l'appel est transmis à l'outil", etat["args"].get("id_question") == "c1", str(etat["args"]))
etat["duree"] = 4  # plus long que le réglage (2 s + 1 s de marge)
debut = time.time()
resultat = appeler("poser_question", {"question": "{}", "bloquante": "true", "id_question": "c2"}, table)
verifier("5 mais pas au delà du réglage (+ marge)", "Délai dépassé" in resultat and 2.5 < time.time() - debut < 3.7, f"{time.time() - debut:.1f}s")

# Injection de l'identifiant par _executer_un_appel
vus = {}
ns2 = {
    "json": json, "NOM_OUTIL_QUESTION": q.NOM_OUTIL_QUESTION,
    "appeler_outil": lambda nom, arguments, table, arret=None: vus.update(nom=nom, arguments=dict(arguments)) or "ok",
}
exec(compile(extraire("core/execution_outils.py", {"_executer_un_appel"}), "execution_extrait", "exec"), ns2)
ns2["_executer_un_appel"]({"id": "call_9", "name": "poser_question", "arguments": json.dumps({"question": "{}", "id_question": "pirate"})}, {})
verifier("6 l'identifiant du serveur écrase celui du modèle", vus["arguments"].get("id_question") == "call_9", str(vus))
ns2["_executer_un_appel"]({"id": "call_10", "name": "autre_outil", "arguments": "{}"}, {})
verifier("7 les autres outils ne reçoivent pas d'identifiant", "id_question" not in vus["arguments"], str(vus))

print()
print("TOUT EST OK" if not echecs else f"ECHECS : {echecs}")
sys.exit(1 if echecs else 0)
