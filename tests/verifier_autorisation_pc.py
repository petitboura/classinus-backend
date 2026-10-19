"""Verifie le bloc `autorisation` envoye a l'application PC (19/10/2026) : eteint par defaut, allume par variable d'environnement."""
import asyncio
from types import SimpleNamespace

import serveur_canal_pc  # noqa: F401  (installe les remplacements de test avant l'import des outils)
from core import outils_action_agent_pc as outils

recus = []


async def demander(user_id, action, parametres, on_statut=None, delai_abandon_secondes=None):
    recus.append((action, dict(parametres), delai_abandon_secondes))
    return {"ok": True}


async def pas_de_blocage(*_args, **_kwargs):
    return None


async def relecture_factice(user_id, message, delai):
    return message


outils._demander_action_systeme = demander
outils._lecture_prealable_si_necessaire = pas_de_blocage
outils._relire_apres_action = relecture_factice

requete = SimpleNamespace(query_params={"user_id": "u1", "conversation_id": "c1"})
ctx = SimpleNamespace(request_context=SimpleNamespace(request=requete))


async def lancer_actions():
    recus.clear()
    await outils.taper_clavier("bonjour", "Bloc-notes", ctx)
    await outils.appuyer_touches("ctrl+c", ctx)
    await outils.ouvrir_application("notepad", ctx)
    await outils.cliquer_ecran(10, 20, ctx)
    await outils._lire_ecran_pour_modele("u1", automatique=False)
    await outils._lire_ecran_pour_modele("u1", automatique=True)
    return list(recus)


async def principal():
    # 1. ETEINT (par defaut) : aucun bloc, aucun delai d'abandon change pour clic et lecture.
    outils.AUTORISATION_PC_ACTIVE = False
    envoyes = await lancer_actions()
    assert [a for a, _, _ in envoyes] == ["taper_clavier", "appuyer_touches", "ouvrir_application", "cliquer_ecran", "lire_ecran", "lire_ecran"], envoyes
    for action, parametres, abandon in envoyes:
        assert "autorisation" not in parametres, f"{action} : bloc envoye alors que c'est eteint"
    assert envoyes[3][2] is None and envoyes[4][2] is None and envoyes[5][2] is None, "abandon change alors que c'est eteint"
    assert envoyes[0][2] is not None, "taper_clavier garde son abandon allonge (ancien comportement)"

    # 2. ALLUME : le bloc est envoye avec taper, touches, ouvrir, cliquer et lire ; la lecture automatique n'attend jamais.
    outils.AUTORISATION_PC_ACTIVE = True
    envoyes = await lancer_actions()
    for action, parametres, abandon in envoyes:
        bloc = parametres.get("autorisation")
        assert isinstance(bloc, dict) and bloc.get("active") is True, f"{action} : bloc absent"
        assert bloc["applications_sensibles"] and bloc["mots_titre_sensibles"], f"{action} : listes vides"
        assert bloc["actions"] == ["lire", "ecrire", "ouvrir", "cliquer"], bloc["actions"]
        assert "applications_toujours" not in bloc, "les 'toujours' ne sont pas memorises cote serveur pour l'instant"
        assert isinstance(parametres.get("delai_autorisation_ms"), int), f"{action} : delai d'accord absent"
    assert envoyes[3][2] is not None and envoyes[3][2] >= outils.DELAI_AUTORISATION_PC_MS / 1000 + 30, "clic : abandon trop court"
    assert envoyes[4][2] is not None, "lecture demandee par l'IA : abandon trop court"
    assert envoyes[5][2] is None, "lecture automatique : ne doit jamais attendre un accord"
    assert envoyes[5][1]["automatique"] is True and envoyes[4][1]["automatique"] is False

    # 3. Textes facultatifs : envoyes seulement quand la variable est renseignee.
    import os
    assert "message_risque" not in outils._parametres_autorisation()["autorisation"]
    os.environ["CLASSINUS_PC_MESSAGE_RISQUE"] = "Texte de test"
    os.environ["CLASSINUS_PC_ACTIONS_CONTROLEES"] = "lire, cliquer"
    bloc = outils._parametres_autorisation()["autorisation"]
    assert bloc["message_risque"] == "Texte de test" and bloc["actions"] == ["lire", "cliquer"], bloc
    print("OK : bloc autorisation eteint par defaut, envoye partout quand allume, lecture automatique sans attente.")


asyncio.run(principal())
