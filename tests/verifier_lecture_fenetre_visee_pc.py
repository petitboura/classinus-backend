"""Verifie la lecture d'une fenetre derriere avec lire_ecran(fenetre=...) (13/10/2026)."""
import asyncio
from types import SimpleNamespace

import serveur_canal_pc  # noqa: F401  (installe les remplacements de test avant l'import des outils)
from core import lecture_ecran_continue
from core import outils_action_agent_pc as outils

demandes = []
reponse = {}


async def demander(user_id, action, parametres, on_statut=None, delai_abandon_secondes=None):
    demandes.append((action, dict(parametres)))
    return dict(reponse)


outils._demander_action_systeme = demander


def ctx_pour(conversation_id):
    requete = SimpleNamespace(query_params={"user_id": "u1", "conversation_id": conversation_id})
    return SimpleNamespace(request_context=SimpleNamespace(request=requete))


DERRIERE = {
    "titre_fenetre_active": "Sans titre - Bloc-notes", "application": "notepad", "fenetre_classinus": False,
    "fenetres_ouvertes": ["Navigateur"], "mode": "uia", "coupe": False, "zone_lue": "fenetre", "fenetre_visee": True,
    "elements": [
        {"type": "champ", "nom": "Zone de texte", "valeur": "bonjour", "x": 300, "y": 400, "gauche": 100, "haut": 200, "largeur": 400, "hauteur": 300},
    ],
}
DEVANT = {**DERRIERE, "fenetre_visee": False}


async def verifier():
    # 1. Formatage : la fenetre derriere est annoncee comme telle, ses positions ne sont jamais « clic possible ».
    texte = outils._formater_lecture_ecran(DERRIERE)
    assert "Fenêtre lue sans être mise devant : « Sans titre - Bloc-notes » (notepad)" in texte, texte
    assert "Fenêtre au premier plan" not in texte, texte
    assert "clic possible" not in texte and "position (300, 400)" in texte, texte
    assert "n'utilise PAS cliquer_ecran" in texte and "valeur : « bonjour »" in texte, texte

    # 2. Lecture normale inchangee.
    texte = outils._formater_lecture_ecran(DEVANT)
    assert texte.startswith("Fenêtre au premier plan : « Sans titre - Bloc-notes » (notepad)"), texte
    assert "clic possible en (300, 400)" in texte and "utilisables avec cliquer_ecran" in texte, texte

    ctx = ctx_pour("c-derriere")

    # 3. Fenetre derriere : le titre part a l'application PC, et ce n'est PAS une premiere lecture de l'ecran.
    reponse.clear(); reponse.update(DERRIERE); demandes.clear()
    texte = await outils.lire_ecran(ctx, "fenetre", "  Bloc-notes  ")
    assert demandes and demandes[0][0] == "lire_ecran" and demandes[0][1]["fenetre_cible"] == "Bloc-notes", demandes
    assert demandes[0][1]["zone"] == "fenetre" and demandes[0][1]["automatique"] is False, demandes
    assert "Fenêtre lue sans être mise devant" in texte, texte
    assert not lecture_ecran_continue.a_deja_lu("u1", "c-derriere"), "lire une fenetre derriere ne deverrouille pas les actions"

    # 4. Lecture normale : aucun parametre fenetre_cible, et premiere lecture enregistree.
    reponse.clear(); reponse.update(DEVANT); demandes.clear()
    await outils.lire_ecran(ctx, "fenetre", "")
    assert "fenetre_cible" not in demandes[0][1], demandes
    assert lecture_ecran_continue.a_deja_lu("u1", "c-derriere")

    # 5. Fenetre + autre zone : refus clair, rien n'est demande a l'application PC.
    demandes.clear()
    texte = await outils.lire_ecran(ctx, "bureau", "Bloc-notes")
    assert texte.startswith("Erreur : le paramètre fenetre ne se combine pas avec zone"), texte
    assert not demandes, demandes

    # 6. Echec cote PC (introuvable, plusieurs, reduite) : l'erreur est rendue telle quelle, jamais de repli.
    reponse.clear(); reponse.update({"erreur": "Lecture de l'écran impossible : Aucune fenêtre ouverte ne correspond à « X ». Fenêtres lisibles : « Navigateur »"})
    texte = await outils.lire_ecran(ctx_pour("c2"), "fenetre", "X")
    assert texte.startswith("Erreur : ") and "Fenêtres lisibles : « Navigateur »" in texte, texte
    assert not lecture_ecran_continue.a_deja_lu("u1", "c2")

    # 6 bis. Application PC ancienne : elle lit la fenetre du premier plan sans dire fenetre_visee,
    #        le modele ne doit pas croire avoir lu la fenetre voulue.
    reponse.clear(); reponse.update(DEVANT)
    texte = await outils.lire_ecran(ctx_pour("c4"), "fenetre", "Bloc-notes")
    assert texte.startswith("Erreur : l'application Classinus du PC") and "Fenêtre au premier plan" not in texte, texte
    assert not lecture_ecran_continue.a_deja_lu("u1", "c4")

    # 7. Une lecture automatique du serveur ne peut jamais viser une fenetre derriere.
    outils_requete = ctx_pour("c3")
    outils_requete.request_context.request.query_params["automatique"] = "1"
    reponse.clear(); reponse.update(DEVANT); demandes.clear()
    await outils.lire_ecran(outils_requete, "fenetre", "Bloc-notes")
    assert "fenetre_cible" not in demandes[0][1], demandes

    print("OK : lecture d'une fenetre derriere (formatage, positions non cliquables, verrou de premiere lecture, erreurs).")


asyncio.run(verifier())
