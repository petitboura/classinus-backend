"""Test de connexion réelle, sans audio et sans journaliser clé ou jeton.

Exécution depuis la racine : python scripts/verifier_gemini_live.py
Le déploiement de test utilise ce script avant de remplacer le service actif.
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google import genai
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed
from core.gemini_live_config import reglages_gemini_live, version_api_gemini_live


def verifier():
    reglages = reglages_gemini_live()
    version = version_api_gemini_live(reglages["url"])
    cle = os.environ.get("GOOGLE_API_KEY")
    if not cle:
        raise RuntimeError("GOOGLE_API_KEY absente")
    maintenant = datetime.now(timezone.utc)
    with genai.Client(api_key=cle) as client:
        token = client.auth_tokens.create(config={
            "uses": 1,
            "expire_time": maintenant + timedelta(minutes=2),
            "new_session_expire_time": maintenant + timedelta(minutes=1),
            "http_options": {"api_version": version},
        })
    setup = {
        "model": "models/" + reglages["model"],
        "generationConfig": {"responseModalities": ["AUDIO"]},
        "systemInstruction": {"parts": [{"text": reglages["consignes"]}]},
        "inputAudioTranscription": {}, "outputAudioTranscription": {},
    }
    if reglages["proactivite"]:
        setup["proactivity"] = {"proactiveAudio": True}
    print(f"GEMINI_LIVE_TEST version={version} proactivite={reglages['proactivite']}", flush=True)
    with connect(reglages["url"] + "?access_token=" + quote(token.name, safe=""),
                 open_timeout=15, close_timeout=3) as ws:
        ws.send(json.dumps({"setup": setup}))
        message = json.loads(ws.recv(timeout=15))
        if "setupComplete" not in message:
            raise RuntimeError("setupComplete absent")
    print("GEMINI_LIVE_TEST setupComplete OK", flush=True)


if __name__ == "__main__":
    try:
        verifier()
    except ConnectionClosed as erreur:
        code = erreur.rcvd.code if erreur.rcvd else None
        raison = erreur.rcvd.reason if erreur.rcvd else ""
        # Ne jamais écrire l'URL de connexion (elle contient le jeton).
        champ_refuse = 'Unknown name "proactivity"' in raison
        print(f"GEMINI_LIVE_TEST ECHEC code={code} proactivity_refusee={champ_refuse}", flush=True)
        sys.exit(1)
    except Exception as erreur:
        print(f"GEMINI_LIVE_TEST ECHEC type={type(erreur).__name__}", flush=True)
        sys.exit(1)
