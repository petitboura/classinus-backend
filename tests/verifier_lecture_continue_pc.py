"""
Verrou "premiere lecture" et lecture continue des actions PC (30/09/2026).

Vrais outils (core/outils_action_agent_pc.py), seul le transport vers
l'application PC est remplace par un faux qui enregistre chaque demande.
Verifie : aucune action executee tant que l'ecran n'a pas ete lu dans la
conversation, l'ecran renvoye a la place de l'action, mode continu ensuite
(chaque action renvoie l'etat de l'ecran qui suit), une nouvelle conversation
remet le verrou, un echec de lecture ne l'ouvre pas, et lire_ecran et
lire_page restent sans renvoi l'un vers l'autre.
"""
import asyncio
from types import SimpleNamespace

import serveur_canal_pc  # noqa: F401  (installe les remplacements de test avant l'import des outils)
from core import lecture_ecran_continue
from core import outils_action_agent_pc as outils

outils.DELAI_APRES_CLIC_SECONDES = 0
outils.DELAI_APRES_CLAVIER_SECONDES = 0
outils.DELAI_APRES_OUVERTURE_SECONDES = 0

LECTURE = {
    "titre_fenetre_active": "Bloc-notes test", "application": "notepad", "fenetre_classinus": False,
    "mode": "uia", "elements": [{"type": "texte", "nom": "Texte Windows vérifié", "x": 10, "y": 20}],
}


def ctx_pour(conversation_id):
    parametres = {"user_id": "test-pc"}
    if conversation_id:
        parametres["conversation_id"] = conversation_id
    return SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(query_params=parametres)))


# Valeur du drapeau "automatique" envoyee a l'application PC a chaque lecture.
drapeaux_automatique = []


def installer_faux_transport(lecture=LECTURE, reponses_actions=None):
    appels = []

    async def demander(user_id, action, parametres, on_statut=None):
        appels.append(action)
        if action == "lire_ecran":
            drapeaux_automatique.append(parametres.get("automatique"))
        if action == "lire_ecran":
            return lecture
        return (reponses_actions or {}).get(action, {"ok": True})

    outils._demander_action_systeme = demander
    return appels


async def verifier():
    # 1. Premiere action : rien n'est execute, l'ecran est renvoye.
    lecture_ecran_continue._lectures_faites.clear()
    appels = installer_faux_transport()
    texte = await outils.cliquer_ecran(10, 20, ctx_pour("conv-A"))
    assert appels == ["lire_ecran"], appels
    assert "NON exécutée" in texte and "Texte Windows vérifié" in texte, texte
    assert lecture_ecran_continue.a_deja_lu("test-pc", "conv-A")

    # 2. Mode continu : l'action s'execute puis renvoie l'etat de l'ecran qui suit.
    appels = installer_faux_transport(reponses_actions={"cliquer_ecran": {"ok": True, "curseur_reel_utilise": False}})
    texte = await outils.cliquer_ecran(10, 20, ctx_pour("conv-A"))
    assert appels == ["cliquer_ecran", "lire_ecran"], appels
    assert "Clic effectué" in texte and "État de l'écran après l'action" in texte and "Texte Windows vérifié" in texte, texte
    assert "NON exécutée" not in texte

    # 3. Les autres actions PC suivent la meme regle.
    for nom_action, appel in (
        ("taper_clavier", lambda c: outils.taper_clavier("bonjour", c)),
        ("appuyer_touches", lambda c: outils.appuyer_touches("ctrl+c", c)),
        ("ouvrir_application", lambda c: outils.ouvrir_application("notepad", c)),
    ):
        lecture_ecran_continue._lectures_faites.clear()
        appels = installer_faux_transport(reponses_actions={"appuyer_touches": {"ok": True, "combinaisons": ["Ctrl+C"]}})
        bloque = await appel(ctx_pour("conv-B"))
        assert appels == ["lire_ecran"] and "NON exécutée" in bloque, (nom_action, appels, bloque)
        appels = installer_faux_transport(reponses_actions={"appuyer_touches": {"ok": True, "combinaisons": ["Ctrl+C"]}})
        texte = await appel(ctx_pour("conv-B"))
        assert appels == [nom_action, "lire_ecran"], (nom_action, appels)
        assert "État de l'écran après l'action" in texte, texte
    texte = await outils.appuyer_touches("ctrl+c", ctx_pour("conv-B"))
    assert "Touches pressées : Ctrl+C." in texte, texte

    # 4. Une autre conversation repart de zero.
    appels = installer_faux_transport()
    texte = await outils.taper_clavier("bonjour", ctx_pour("conv-C"))
    assert appels == ["lire_ecran"] and "NON exécutée" in texte, (appels, texte)

    # 5. Un echec de lecture n'ouvre pas le verrou et n'execute rien.
    lecture_ecran_continue._lectures_faites.clear()
    for echec in (None, {"erreur": "delai depasse"}, "pas un dict"):
        appels = installer_faux_transport(lecture=echec)
        texte = await outils.cliquer_ecran(1, 1, ctx_pour("conv-D"))
        assert appels == ["lire_ecran"] and "NON exécutée" in texte, (echec, appels, texte)
        assert not lecture_ecran_continue.a_deja_lu("test-pc", "conv-D"), echec

    # 6. Un echec d'action ne declenche pas de relecture (erreur renvoyee telle quelle).
    lecture_ecran_continue.marquer_lu("test-pc", "conv-E")
    appels = installer_faux_transport(reponses_actions={"taper_clavier": {"erreur": "texte vide"}})
    texte = await outils.taper_clavier("x", ctx_pour("conv-E"))
    assert appels == ["taper_clavier"] and texte == "Erreur : texte vide", (appels, texte)

    # 7. lire_ecran explicite compte comme premiere lecture.
    lecture_ecran_continue._lectures_faites.clear()
    appels = installer_faux_transport()
    await outils.lire_ecran(ctx_pour("conv-F"))
    assert lecture_ecran_continue.a_deja_lu("test-pc", "conv-F")
    appels = installer_faux_transport()
    await outils.taper_clavier("x", ctx_pour("conv-F"))
    assert appels == ["taper_clavier", "lire_ecran"], appels

    # 7 bis. Une lecture decidee par le serveur est marquee automatique (l'application PC
    # ne l'affiche pas), celle que l'IA demande elle-meme ne l'est jamais.
    lecture_ecran_continue._lectures_faites.clear()
    drapeaux_automatique.clear()
    installer_faux_transport()
    await outils.cliquer_ecran(10, 20, ctx_pour("conv-G"))
    assert drapeaux_automatique == [True], drapeaux_automatique
    drapeaux_automatique.clear()
    installer_faux_transport()
    await outils.cliquer_ecran(10, 20, ctx_pour("conv-G"))
    assert drapeaux_automatique == [True], drapeaux_automatique
    drapeaux_automatique.clear()
    installer_faux_transport()
    await outils.lire_ecran(ctx_pour("conv-G"))
    assert drapeaux_automatique == [False], drapeaux_automatique
    drapeaux_automatique.clear()
    installer_faux_transport()
    ctx_auto = ctx_pour("conv-G")
    ctx_auto.request_context.request.query_params["automatique"] = "1"
    await outils.lire_ecran(ctx_auto)
    assert drapeaux_automatique == [True], drapeaux_automatique

    # 8. Separation lire_ecran / lire_page : aucun renvoi de l'un vers l'autre.
    classinus_seul = dict(LECTURE, fenetre_classinus=True)
    texte = outils._formater_lecture_ecran(classinus_seul)
    assert "lire_page" not in texte and "Classinus" in texte, texte
    from core import outils_action_agent
    assert "lire_ecran" not in outils_action_agent.lire_page.__doc__
    assert "lire_page" not in outils.lire_ecran.__doc__ and "lire_page" not in outils.MESSAGE_LECTURE_PREALABLE

    # 9. Aucun identifiant de conversation : etat partage par utilisateur, verrou quand meme actif.
    lecture_ecran_continue._lectures_faites.clear()
    appels = installer_faux_transport()
    await outils.cliquer_ecran(1, 1, ctx_pour(None))
    assert appels == ["lire_ecran"], appels
    print("OK : verrou premiere lecture, lecture continue apres action, separation lire_ecran / lire_page.")


if __name__ == "__main__":
    asyncio.run(verifier())
