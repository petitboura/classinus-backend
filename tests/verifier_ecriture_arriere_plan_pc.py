"""Verifie le message renvoye au modele apres une ecriture en arriere plan (12/10/2026)."""
import asyncio
from types import SimpleNamespace

import serveur_canal_pc  # noqa: F401  (installe les remplacements de test avant l'import des outils)
from core import outils_action_agent_pc as outils

reponse = {}
messages = []


async def demander(user_id, action, parametres, on_statut=None, delai_abandon_secondes=None):
    return dict(reponse)


async def pas_de_blocage(*_args, **_kwargs):
    return None


async def relecture_factice(user_id, message, delai):
    messages.append(message)
    return message


outils._demander_action_systeme = demander
outils._lecture_prealable_si_necessaire = pas_de_blocage
outils._relire_apres_action = relecture_factice

requete = SimpleNamespace(query_params={"user_id": "u1", "conversation_id": "c1"})
ctx = SimpleNamespace(request_context=SimpleNamespace(request=requete))


async def principal():
    # Ecriture en arriere plan : le modele doit savoir que l'ecran renvoye n'est pas celui de la fenetre visee.
    reponse.update({"ok": True, "mode": "arriere_plan", "fenetre": "Sans titre - Bloc-notes"})
    texte = await outils.taper_clavier("bonjour", "Bloc-notes", ctx)
    assert "arrière plan" in texte and "Sans titre - Bloc-notes" in texte, texte
    assert "à la fin" in texte and "pas celui de cette fenêtre" in texte, texte
    assert 'lire_ecran avec fenetre="Sans titre - Bloc-notes"' in texte, texte

    # Frappe normale : message d'avant, inchange.
    reponse.clear()
    reponse.update({"ok": True})
    texte = await outils.taper_clavier("bonjour", "Bloc-notes", ctx)
    assert texte == "Texte tapé au clavier avec succès.", texte

    # Echec : l'erreur est renvoyee telle quelle.
    reponse.clear()
    reponse.update({"erreur": "Texte NON tapé : test"})
    texte = await outils.taper_clavier("bonjour", "Bloc-notes", ctx)
    assert texte == "Erreur : Texte NON tapé : test", texte
    print("OK : message d'ecriture en arriere plan, frappe normale et erreur.")


asyncio.run(principal())
