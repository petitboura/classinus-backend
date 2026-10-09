"""Verifie que les outils clavier et ouverture envoient au PC la liste des applications protegees et le delai d'accord (08/10/2026)."""
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


async def principal():
    await outils.taper_clavier("bonjour", ctx)
    await outils.appuyer_touches("ctrl+c", ctx)
    await outils.ouvrir_application("notepad", ctx)

    assert [r[0] for r in recus] == ["taper_clavier", "appuyer_touches", "ouvrir_application"], recus
    for action, parametres, abandon in recus:
        liste = parametres.get("applications_protegees")
        assert isinstance(liste, list) and liste, f"{action} : liste absente"
        for attendu in ("powershell", "cmd", "windowsterminal", "bitwarden", "regedit", "systemsettings"):
            assert attendu in liste, f"{action} : {attendu} manque"
        assert "code" not in liste and "notepad" not in liste, f"{action} : les editeurs ne doivent pas etre proteges"
        assert all(nom == nom.lower() and not nom.endswith(".exe") for nom in liste), f"{action} : noms mal formes"
        assert parametres.get("delai_autorisation_ms") == outils.DELAI_AUTORISATION_PC_MS, f"{action} : delai absent"
        assert abandon is not None and abandon >= outils.DELAI_AUTORISATION_PC_MS / 1000 + 30, f"{action} : abandon trop court"
    # Les parametres propres a chaque action sont conserves.
    assert recus[0][1]["texte"] == "bonjour"
    assert recus[1][1]["touches"] == "ctrl+c"
    assert recus[2][1]["nom"] == "notepad"
    print("OK : applications protegees et delai d'accord envoyes avec taper_clavier, appuyer_touches et ouvrir_application.")


asyncio.run(principal())
