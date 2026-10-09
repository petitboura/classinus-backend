"""Verifie la lecture de l'ecran lancee en parallele de la preparation du tour (04/10/2026)."""
import os
import sys
import threading
import time

import serveur_canal_pc  # noqa: F401  (installe les remplacements de test avant l'import des modules)
from core import ecran_pc_continu, lecture_ecran_continue
import types

TABLE = {"lire_ecran": {"url": "http://x/mcp?user_id=u1&conversation_id=c1", "headers": {}}, "autre": {"url": "http://x/autre"}}
urls_appelees = []
fils_appel = []


def faux_appeler_outil(nom, arguments, table):
    urls_appelees.append(table[nom]["url"])
    fils_appel.append(threading.current_thread().name)
    time.sleep(0.3)
    return "Fenêtre au premier plan : « Bloc-notes »"


# Faux module d'outils : le vrai a besoin de la base de donnees, inutile pour ce test.
faux_module = types.ModuleType("core.mcp_tools")
faux_module.appeler_outil = faux_appeler_outil
sys.modules["core.mcp_tools"] = faux_module


def verifier():
    lecture_ecran_continue._lectures_faites.clear()
    lecture_ecran_continue.marquer_lu("u1", "c1")

    # 1. La lecture est lancee en arriere-plan : le lancement rend la main tout de suite.
    debut = time.monotonic()
    futur = ecran_pc_continu.lancer_lecture_anticipee("u1", "c1", TABLE)
    assert futur is not None and time.monotonic() - debut < 0.2
    # Pendant ce temps le tour se prepare (simule) : la reprise n'attend que le reste.
    time.sleep(0.3)
    debut = time.monotonic()
    texte = ecran_pc_continu.bloc_etat_ecran_pc_anticipe(futur, "u1", "c1", TABLE)
    assert time.monotonic() - debut < 0.15, "la lecture aurait du etre deja finie"
    assert "Bloc-notes" in texte and "lu automatiquement" in texte, texte
    # La lecture est marquee automatique dans l'adresse (l'IA ne peut pas la modifier).
    assert urls_appelees[-1].endswith("&automatique=1"), urls_appelees
    assert fils_appel[-1].startswith("ecran-pc"), fils_appel

    # 2. Sans lecture lancee, meme resultat qu'avant.
    texte2 = ecran_pc_continu.bloc_etat_ecran_pc_anticipe(None, "u1", "c1", TABLE)
    assert "Bloc-notes" in texte2

    # 3. Si l'outil n'est pas propose a ce tour, rien n'est ajoute meme si la lecture a eu lieu.
    futur = ecran_pc_continu.lancer_lecture_anticipee("u1", "c1", TABLE)
    assert ecran_pc_continu.bloc_etat_ecran_pc_anticipe(futur, "u1", "c1", {"autre": TABLE["autre"]}) == ""

    # 4. Pas de lecture lancee sans outil de lecture ni utilisateur.
    assert ecran_pc_continu.lancer_lecture_anticipee("u1", "c1", {"autre": TABLE["autre"]}) is None
    assert ecran_pc_continu.lancer_lecture_anticipee(None, "c1", TABLE) is None

    # 5. Premiere lecture pas encore faite : rien n'est ajoute (le verrou reste en place).
    lecture_ecran_continue._lectures_faites.clear()
    futur = ecran_pc_continu.lancer_lecture_anticipee("u1", "c1", TABLE)
    assert ecran_pc_continu.bloc_etat_ecran_pc_anticipe(futur, "u1", "c1", TABLE) == ""
    print("OK : lecture de l'ecran anticipee, marquee automatique, sans changer le resultat.")


verifier()
