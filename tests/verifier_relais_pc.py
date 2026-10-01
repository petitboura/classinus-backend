"""Vraie route WS et vrais outils : un seul relais, avec ou sans seconde WS."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import time

from fastapi.testclient import TestClient
from serveur_canal_pc import app, canal


def verifier(avec_renderer: bool, avec_natif: bool):
    with TestClient(app) as client, ExitStack() as pile, ThreadPoolExecutor() as execution:
        connexions = {}
        for nom, relais in (("pc-systeme", False), ("pc", True)):
            if (relais and not avec_renderer) or (not relais and not avec_natif):
                continue
            ws = pile.enter_context(client.websocket_connect("/api/canal-agent-applicatif/ws"))
            ws.send_json({"auth_token": "session-test", "appareil_id": nom,
                          "actions_systeme_via_renderer": relais})
            connexions[nom] = ws
        for _ in range(100):
            if set(client.get("/test/etat").json()["appareils"]) == set(connexions):
                break
            time.sleep(0.01)
        else:
            raise AssertionError("Authentification des canaux non terminée")

        # Observer les véritables envois serveur, y compris le canal qui ne
        # doit rien recevoir : lire celui-ci avec receive_json bloquerait.
        envois = []
        for (_, nom), socket in list(canal._connexions.items()):
            envoyer = socket.send_json
            async def observer(message, *args, nom=nom, envoyer=envoyer, **kwargs):
                envois.append((nom, message))
                await envoyer(message, *args, **kwargs)
            socket.send_json = observer

        reponse = execution.submit(lambda: client.get("/test/lire-ecran").json())
        cible = "pc" if avec_renderer else "pc-systeme"
        message = connexions[cible].receive_json()
        assert message["action_systeme"] == "lire_ecran"
        assert bool(message.get("via_renderer")) == avec_renderer
        connexions[cible].send_json({"id": message["id"], "resultat": {
            "titre_fenetre_active": "Bloc-notes test", "fenetre_classinus": False,
            "mode": "uia", "elements": [{"type": "texte", "nom": "Texte Windows vérifié"}],
        }})
        assert "Texte Windows vérifié" in reponse.result(timeout=5)["texte"]
        assert [nom for nom, m in envois if "action_systeme" in m] == [cible], envois


if __name__ == "__main__":
    verifier(avec_renderer=True, avec_natif=True)
    verifier(avec_renderer=True, avec_natif=False)
    verifier(avec_renderer=False, avec_natif=True)
    assert not canal._relais_systeme, "Capacité périmée après déconnexion"
    print("OK : relais applicatif seul, deux connexions sans doublon, ancienne app compatible.")
