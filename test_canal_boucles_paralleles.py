"""
Outils téléphone en parallèle (04/11/2026) : chaque outil s'exécute dans son propre
fil avec sa propre boucle asyncio.run, alors que les connexions et les verrous du
canal agent applicatif vivent sur la boucle principale du serveur. Avant le
correctif, un seul appel passait et les autres échouaient avec « is bound to a
different event loop » : le message n'était jamais envoyé à l'appli PC.
Sans appel réseau : les connexions sont simulées.
"""

import asyncio
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "dummy")

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "core"))

import pytest

import canal_agent_applicatif as canal

NB_OUTILS = 8
USER = "u-test-boucles"


@pytest.fixture(autouse=True)
def _etat_canal_propre():
    """Remet le module canal dans son état d'origine après chaque test."""
    boucle_avant = canal._boucle_evenements
    yield
    canal._connexions.clear()
    canal._relais_systeme.clear()
    canal._verrous_envoi.clear()
    canal._etat_actions.clear()
    canal._attentes.clear()
    canal._attentes_utilisateur.clear()
    canal._boucle_evenements = boucle_avant


class FausseConnexionPC:
    """Appli PC simulée : répond tout de suite à chaque demande reçue."""

    def __init__(self, boucle):
        self.boucle = boucle
        self.recus = []

    async def send_json(self, message):
        self.recus.append(message)
        # La reponse arrive comme en vrai : par le gestionnaire WebSocket,
        # sur la boucle principale.
        self.boucle.call_soon(canal.recevoir_reponse, message["id"], {"texte": "ok"})

    async def close(self):
        pass


def _lancer_boucle_principale():
    boucle = asyncio.new_event_loop()
    pret = threading.Event()

    def tourner():
        asyncio.set_event_loop(boucle)
        boucle.call_soon(pret.set)
        boucle.run_forever()

    fil = threading.Thread(target=tourner, daemon=True)
    fil.start()
    pret.wait(5)
    return boucle, fil


def _appel_outil(numero):
    """Même chemin que _appeler_outil_telephone_via_app : asyncio.run dans un fil."""
    async def appel():
        if not await canal.a_app_telephone_connectee(USER):
            return "non connectee"
        reponse = await canal.demander_action_systeme(
            USER,
            "outil_telephone",
            {"nom": f"outil_{numero}", "args": {}},
            delai_abandon_secondes=16,
        )
        return reponse

    return asyncio.run(appel())


def test_huit_outils_telephone_en_parallele_recoivent_tous_une_reponse():
    boucle, fil = _lancer_boucle_principale()
    try:
        connexion = FausseConnexionPC(boucle)
        asyncio.run_coroutine_threadsafe(
            canal.connecter(USER, "pc-systeme", connexion, actions_systeme_via_renderer=True),
            boucle,
        ).result(5)

        with ThreadPoolExecutor(max_workers=NB_OUTILS) as pool:
            resultats = list(pool.map(_appel_outil, range(NB_OUTILS)))

        assert resultats == [{"texte": "ok"}] * NB_OUTILS
        assert len(connexion.recus) == NB_OUTILS
    finally:
        boucle.call_soon_threadsafe(boucle.stop)
        fil.join(5)


def test_diagnostic_depuis_un_fil_lit_les_vraies_connexions():
    boucle, fil = _lancer_boucle_principale()
    try:
        connexion = FausseConnexionPC(boucle)
        asyncio.run_coroutine_threadsafe(
            canal.connecter(USER, "pc-systeme", connexion, actions_systeme_via_renderer=True),
            boucle,
        ).result(5)

        texte = asyncio.run(canal.diagnostiquer_app_telephone(USER))
        assert "l'appli PC est bien connectée" in texte
        assert "relais_pc=1" in texte
    finally:
        boucle.call_soon_threadsafe(boucle.stop)
        fil.join(5)


def test_sur_la_boucle_principale_le_comportement_est_inchange():
    async def scenario():
        connexion = FausseConnexionPC(asyncio.get_running_loop())
        await canal.connecter(USER, "pc-systeme", connexion, actions_systeme_via_renderer=True)
        assert await canal.a_app_telephone_connectee(USER) is True
        return await canal.demander_action_systeme(
            USER, "outil_telephone", {"nom": "x", "args": {}}, delai_abandon_secondes=16
        )

    assert asyncio.run(scenario()) == {"texte": "ok"}
