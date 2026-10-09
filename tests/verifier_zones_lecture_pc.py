"""Verifie la lecture du bureau et de la barre des taches avec le meme outil lire_ecran (04/10/2026)."""
import asyncio
from types import SimpleNamespace

import serveur_canal_pc  # noqa: F401  (installe les remplacements de test avant l'import des outils)
from core import lecture_ecran_continue
from core import outils_action_agent_pc as outils

demandes = []


def installer_faux_transport(resultat):
    async def demander(user_id, action, parametres, on_statut=None, delai_abandon_secondes=None):
        demandes.append((action, dict(parametres)))
        return resultat if action == "lire_ecran" else {"ok": True}

    outils._demander_action_systeme = demander


def ctx_pour(conversation_id):
    requete = SimpleNamespace(query_params={"user_id": "u1", "conversation_id": conversation_id})
    return SimpleNamespace(request_context=SimpleNamespace(request=requete))


BARRE = {
    "titre_fenetre_active": None, "application": None, "fenetre_classinus": False,
    "fenetres_ouvertes": ["Bloc-notes"], "mode": "uia", "coupe": False, "zone_lue": "barre_des_taches",
    "elements": [
        {"type": "bouton", "nom": "Démarrer", "x": 40, "y": 1060, "gauche": 20, "haut": 1040, "largeur": 40, "hauteur": 40, "zone": "barre des tâches"},
        {"type": "bouton", "nom": "Horloge", "x": 1850, "y": 1060, "gauche": 1800, "haut": 1040, "largeur": 100, "hauteur": 40, "zone": "barre des tâches"},
    ],
}
BUREAU = {
    "titre_fenetre_active": None, "application": None, "fenetre_classinus": False,
    "fenetres_ouvertes": [], "mode": "uia", "coupe": False, "zone_lue": "bureau",
    "elements": [
        {"type": "élément de liste", "nom": "Corbeille", "x": 40, "y": 50, "gauche": 10, "haut": 20, "largeur": 60, "hauteur": 60, "zone": "bureau"},
    ],
}


async def verifier():
    # 1. Formatage : la barre des taches est annoncee comme telle, ses elements marques "dans la barre des tâches".
    texte = outils._formater_lecture_ecran(BARRE)
    assert texte.startswith("Barre des tâches de Windows"), texte
    assert "Démarrer" in texte and "dans la barre des tâches" in texte and "clic possible en (40, 1060)" in texte, texte
    assert "Aucune fenêtre au premier plan" not in texte, texte

    # 2. Formatage : le bureau.
    texte = outils._formater_lecture_ecran(BUREAU)
    assert texte.startswith("Bureau de Windows"), texte
    assert "Corbeille" in texte and "dans le bureau" in texte, texte

    # 3. Zone vide ou illisible : message clair, jamais une invention.
    vide = dict(BUREAU, elements=[], mode="titre_seul")
    texte = outils._formater_lecture_ecran(vide)
    assert "Rien n'a pu être lu dans le bureau" in texte, texte

    # 4. Lecture normale inchangee (zone absente = fenetre).
    fenetre = {"titre_fenetre_active": "Bloc-notes", "application": "notepad", "fenetre_classinus": False,
               "fenetres_ouvertes": [], "mode": "uia", "coupe": False,
               "elements": [{"type": "champ", "nom": "", "valeur": "bonjour", "x": 5, "y": 6, "gauche": 1, "haut": 2, "largeur": 3, "hauteur": 4}]}
    texte = outils._formater_lecture_ecran(fenetre)
    assert texte.startswith("Fenêtre au premier plan : « Bloc-notes »"), texte

    # 5. L'outil lire_ecran : zone transmise a l'application PC, par defaut "fenetre".
    lecture_ecran_continue._lectures_faites.clear()
    installer_faux_transport(BARRE)
    demandes.clear()
    retour = await outils.lire_ecran(ctx_pour("conv-Z"), zone="barre_des_taches")
    assert retour.startswith("Barre des tâches de Windows"), retour
    assert demandes[-1][0] == "lire_ecran" and demandes[-1][1]["zone"] == "barre_des_taches", demandes
    installer_faux_transport(fenetre)
    await outils.lire_ecran(ctx_pour("conv-Z"))
    assert demandes[-1][1]["zone"] == "fenetre", demandes
    await outils.lire_ecran(ctx_pour("conv-Z"), zone="")
    assert demandes[-1][1]["zone"] == "fenetre", demandes

    # 6. Une zone inconnue est refusee sans rien demander a l'application PC.
    nb = len(demandes)
    retour = await outils.lire_ecran(ctx_pour("conv-Z"), zone="tout l'ecran")
    assert "inconnue" in retour and len(demandes) == nb, retour

    # 7. Les lectures du serveur (apres action) restent sur la fenetre.
    lecture_ecran_continue._lectures_faites.clear()
    lecture_ecran_continue.marquer_lu("u1", "conv-Z")
    installer_faux_transport(fenetre)
    demandes.clear()
    outils.DELAI_APRES_CLIC_SECONDES = 0
    await outils.cliquer_ecran(10, 20, ctx_pour("conv-Z"))
    lectures = [p for a, p in demandes if a == "lire_ecran"]
    assert lectures and all(p["zone"] == "fenetre" and p["automatique"] is True for p in lectures), demandes
    print("OK : lecture du bureau et de la barre des taches avec le meme outil, lecture normale inchangee.")


asyncio.run(verifier())
