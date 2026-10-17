"""Verifie le bureau lu comme une fenetre, le bureau au premier plan annonce, et la lecture legere des
titres (16/10/2026, demande de Bourama : Classinus doit toujours savoir quelle fenetre est devant,
voir le bureau comme une fenetre et savoir qu'on est sur le bureau quand tout est ferme)."""
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


def ctx_pour(conversation_id, **parametres_url):
    requete = SimpleNamespace(query_params={"user_id": "u1", "conversation_id": conversation_id, **parametres_url})
    return SimpleNamespace(request_context=SimpleNamespace(request=requete))


BASE = {"application": None, "fenetre_classinus": False, "coupe": False}
BUREAU_ICONES = [{"type": "élément de liste", "nom": "Corbeille", "x": 40, "y": 50, "gauche": 10, "haut": 20, "largeur": 60, "hauteur": 60, "zone": "bureau"}]
# Tout est ferme ou reduit : le bureau est devant.
BUREAU_DEVANT = {**BASE, "titre_fenetre_active": None, "fenetres_ouvertes": [], "mode": "uia", "zone_lue": "bureau",
                 "bureau_premier_plan": True, "elements": BUREAU_ICONES}
# Le bureau lu a la demande pendant qu'une fenetre est devant : pas "au premier plan".
BUREAU_DEMANDE = {**BASE, "titre_fenetre_active": None, "fenetres_ouvertes": ["Bloc-notes"], "mode": "uia", "zone_lue": "bureau", "elements": BUREAU_ICONES}
FENETRE_COMPLETE = {**BASE, "titre_fenetre_active": "Sans titre - Bloc-notes", "application": "notepad", "fenetres_ouvertes": ["Navigateur"],
                    "mode": "uia", "zone_lue": "fenetre",
                    "elements": [{"type": "champ", "nom": "Zone de texte", "valeur": "bonjour", "x": 300, "y": 400, "gauche": 100, "haut": 200, "largeur": 400, "hauteur": 300}]}
LEGERE = {**BASE, "titre_fenetre_active": "Sans titre - Bloc-notes", "application": "notepad", "fenetres_ouvertes": ["Navigateur"],
          "mode": "titre_seul", "zone_lue": "fenetre", "elements": [], "titres_seuls": True}
LEGERE_BUREAU = {**BASE, "titre_fenetre_active": None, "fenetres_ouvertes": [], "mode": "titre_seul", "zone_lue": "bureau",
                 "bureau_premier_plan": True, "elements": [], "titres_seuls": True}
LEGERE_CLASSINUS = {**BASE, "titre_fenetre_active": "Classinus", "fenetre_classinus": True, "fenetres_ouvertes": [], "mode": "titre_seul",
                    "zone_lue": "fenetre", "elements": []}


async def verifier():
    # 1. Le bureau au premier plan est annonce clairement (plus de simple "Bureau de Windows").
    texte = outils._formater_lecture_ecran(BUREAU_DEVANT)
    assert "Le bureau de Windows est au premier plan" in texte and "l'étudiant est sur le bureau" in texte, texte
    assert "Corbeille" in texte and "Aucune fenêtre au premier plan" not in texte, texte
    # Le bureau lu a la demande, une fenetre etant devant : l'ancien texte, sans dire qu'on est dessus.
    texte = outils._formater_lecture_ecran(BUREAU_DEMANDE)
    assert texte.startswith("Bureau de Windows (icônes") and "est sur le bureau" not in texte, texte

    # 2. Le bureau compte comme une fenetre dans la liste, sauf quand c'est lui qu'on lit.
    texte = outils._formater_lecture_ecran(FENETRE_COMPLETE)
    assert "Autres fenêtres ouvertes : « Navigateur », « Bureau »" in texte, texte
    assert "« Bureau »" not in outils._formater_lecture_ecran(BUREAU_DEVANT)
    assert "« Bureau »" not in outils._formater_lecture_ecran(BUREAU_DEMANDE)

    # 3. Lecture legere : titres seulement, le texte dit que le contenu n'est pas lu.
    texte = outils._formater_lecture_ecran(LEGERE)
    assert texte.startswith("Fenêtre au premier plan : « Sans titre - Bloc-notes » (notepad)"), texte
    assert "« Navigateur », « Bureau »" in texte and "Contenu non lu" in texte and "Appelle lire_ecran" in texte, texte
    assert "n'a pas pu être lu" not in texte, texte
    texte = outils._formater_lecture_ecran(LEGERE_BUREAU)
    assert "l'étudiant est sur le bureau" in texte and "Contenu non lu" in texte, texte
    # Seule Classinus ouverte : message habituel.
    assert "seule Classinus est ouverte" in outils._formater_lecture_ecran(LEGERE_CLASSINUS)

    # 4. fenetre="Bureau" revient a zone="bureau" (casse libre), sans chercher une fenetre de ce titre.
    for nom in ("Bureau", "bureau", "Le Bureau", "DESKTOP"):
        lecture_ecran_continue._lectures_faites.clear()
        installer_faux_transport(BUREAU_DEMANDE)
        demandes.clear()
        retour = await outils.lire_ecran(ctx_pour("conv-B"), fenetre=nom)
        assert demandes[-1][1]["zone"] == "bureau" and "fenetre_cible" not in demandes[-1][1], (nom, demandes)
        assert "Corbeille" in retour, retour
    # Un vrai titre de fenetre reste lu comme une fenetre.
    installer_faux_transport({**FENETRE_COMPLETE, "fenetre_visee": True})
    await outils.lire_ecran(ctx_pour("conv-B"), fenetre="Bloc-notes")
    assert demandes[-1][1]["fenetre_cible"] == "Bloc-notes" and demandes[-1][1]["zone"] == "fenetre", demandes
    # La barre des taches ne se combine toujours pas avec une fenetre, meme "Bureau".
    nb = len(demandes)
    retour = await outils.lire_ecran(ctx_pour("conv-B"), zone="barre_des_taches", fenetre="Bureau")
    assert "ne se combine pas" in retour and len(demandes) == nb, retour

    # 5. Lecture legere par le serveur : transmise a l'application PC, ne vaut PAS premiere lecture.
    lecture_ecran_continue._lectures_faites.clear()
    installer_faux_transport(LEGERE)
    demandes.clear()
    retour = await outils.lire_ecran(ctx_pour("conv-L", automatique="1", titres_seuls="1"))
    assert demandes[-1][1]["titres_seuls"] is True and demandes[-1][1]["automatique"] is True, demandes
    assert "Contenu non lu" in retour, retour
    assert not lecture_ecran_continue.a_deja_lu("u1", "conv-L"), "une lecture legere ne vaut pas premiere lecture"

    # 6. L'IA ne peut pas demander la lecture legere : sans "automatique" dans l'adresse, c'est une lecture normale.
    installer_faux_transport(FENETRE_COMPLETE)
    demandes.clear()
    await outils.lire_ecran(ctx_pour("conv-L", titres_seuls="1"))
    assert "titres_seuls" not in demandes[-1][1], demandes
    assert lecture_ecran_continue.a_deja_lu("u1", "conv-L")

    # 7. Application PC ancienne (elle ignore titres_seuls et lit tout) ou repli apres echec : jamais une
    # fausse lecture legere, rien n'est donne au modele.
    for ancien in (FENETRE_COMPLETE, {**LEGERE, "titres_seuls": False, "erreur_lecture": "PowerShell"}):
        lecture_ecran_continue._lectures_faites.clear()
        installer_faux_transport(ancien)
        retour = await outils.lire_ecran(ctx_pour("conv-A", automatique="1", titres_seuls="1"))
        assert retour.startswith("Erreur"), retour
        assert not lecture_ecran_continue.a_deja_lu("u1", "conv-A")

    # 8. Aucun tiret long dans les textes envoyes au modele (preference de Bourama).
    for t in (outils._formater_lecture_ecran(BUREAU_DEVANT), outils._formater_lecture_ecran(LEGERE)):
        assert "\u2014" not in t and "--" not in t, t

    print("OK : bureau lu comme une fenetre, bureau au premier plan annonce, lecture legere des titres.")


asyncio.run(verifier())
