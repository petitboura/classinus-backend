import base64
import json
import os
import subprocess
import tempfile
import threading
import traceback
import urllib.error
import urllib.request

from fastapi import FastAPI, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

MODEL_NAME = os.environ.get("MODEL_NAME", "RobotsMali/soloni-114m-tdt-ctc-v3")

# Transcripteur Gemini : appel direct à l'API Google, sans bibliothèque en plus.
# Clé : GOOGLE_API_KEY (la même que Classinus). Modèle réglable par GEMINI_STT_MODELE.
GEMINI_STT_MODELE_DEFAUT = "gemini-3.5-transcribe"
GEMINI_STT_ADRESSE = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"
GEMINI_STT_DELAI_DEFAUT = 120

app = FastAPI()
etat = {"modele": None, "pret": False, "erreur": None}


def cle_google() -> str:
    return (os.environ.get("GOOGLE_API_KEY") or "").strip()


def modele_gemini() -> str:
    return (os.environ.get("GEMINI_STT_MODELE") or "").strip() or GEMINI_STT_MODELE_DEFAUT


def delai_gemini() -> int:
    try:
        valeur = int((os.environ.get("GEMINI_DELAI_S") or "").strip())
    except ValueError:
        return GEMINI_STT_DELAI_DEFAUT
    return valeur if valeur > 0 else GEMINI_STT_DELAI_DEFAUT


def charger_modele():
    try:
        import nemo.collections.asr as nemo_asr
        etat["modele"] = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.from_pretrained(model_name=MODEL_NAME)
        etat["pret"] = True
    except Exception as e:
        etat["erreur"] = str(e)


threading.Thread(target=charger_modele, daemon=True).start()


class ErreurTranscription(Exception):
    def __init__(self, statut: int, message: str, detail: str | None = None):
        super().__init__(message)
        self.statut = statut
        self.message = message
        self.detail = detail


def transcrire_gemini(wav: bytes) -> str:
    """Envoie le son (WAV) à Gemini et renvoie le texte. Langue détectée par Gemini.

    Le bambara n'est pas dans sa liste de langues : ce moteur sert à vérifier ce qu'il en fait.
    """
    cle = cle_google()
    if not cle:
        raise ErreurTranscription(500, "La clé Google n'est pas configurée dans ce service (variable GOOGLE_API_KEY).")
    corps = {
        "contents": [{
            "role": "user",
            "parts": [{"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav).decode("ascii")}}],
        }],
        "generationConfig": {"audioTranscriptionConfig": {"languageCodes": []}},
    }
    requete = urllib.request.Request(
        GEMINI_STT_ADRESSE.format(modele=modele_gemini()),
        data=json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": cle},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=delai_gemini()) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:1500]
        print("Gemini transcription : erreur HTTP", e.code, detail, flush=True)
        if e.code == 429:
            message = "Google refuse pour l'instant (quota atteint). Réessaie dans un moment."
        elif e.code in (401, 403):
            message = "Google a refusé la clé ou le modèle (clé invalide, ou accès à ce modèle non autorisé)."
        elif e.code == 404:
            message = "Google ne connaît pas ce modèle de transcription (vérifie GEMINI_STT_MODELE)."
        elif e.code == 400:
            message = "Google a refusé cette demande (son trop long ou format non accepté)."
        else:
            message = f"Google a renvoyé une erreur ({e.code})."
        raise ErreurTranscription(502, message, detail)
    except Exception as e:
        trace = traceback.format_exc()
        print(trace, flush=True)
        raise ErreurTranscription(502, "Impossible de joindre Google : " + str(e), trace)
    morceaux = []
    for candidat in (donnees.get("candidates") or []):
        for partie in ((candidat.get("content") or {}).get("parts") or []):
            if partie.get("text"):
                morceaux.append(partie["text"])
    if not morceaux:
        detail = json.dumps(
            {"promptFeedback": donnees.get("promptFeedback"),
             "finishReason": [c.get("finishReason") for c in (donnees.get("candidates") or [])]},
            ensure_ascii=False,
        )
        print("Gemini transcription : aucun texte dans la réponse", detail, flush=True)
        raise ErreurTranscription(502, "Gemini n'a renvoyé aucun texte pour ce son.", detail)
    return "".join(morceaux).strip()


def transcrire_soloni(chemin_wav: str) -> str:
    if not etat["pret"]:
        raise ErreurTranscription(503, "Le modèle charge encore, réessaie dans une minute.")
    try:
        resultat = etat["modele"].transcribe([chemin_wav])
        if isinstance(resultat, tuple):
            resultat = resultat[0]
        premier = resultat[0]
        return premier.text if hasattr(premier, "text") else str(premier)
    except Exception as e:
        trace = traceback.format_exc()
        print(trace, flush=True)
        raise ErreurTranscription(500, "Échec de la transcription : " + str(e), trace)


@app.get("/")
def accueil():
    return FileResponse("index.html")


@app.get("/etat")
def etat_modele():
    return {
        "pret": etat["pret"],
        "erreur": etat["erreur"],
        "modele": MODEL_NAME,
        "gemini": {"disponible": bool(cle_google()), "modele": modele_gemini()},
    }


@app.post("/transcrire")
async def transcrire(moteur: str = "soloni", fichier: UploadFile = File(...)):
    if moteur not in ("soloni", "gemini"):
        return JSONResponse({"erreur": "Moteur inconnu."}, status_code=400)
    if moteur == "soloni" and not etat["pret"]:
        return JSONResponse({"erreur": "Le modèle charge encore, réessaie dans une minute."}, status_code=503)
    if moteur == "gemini" and not cle_google():
        return JSONResponse(
            {"erreur": "La clé Google n'est pas configurée dans ce service (variable GOOGLE_API_KEY)."},
            status_code=500,
        )
    with tempfile.TemporaryDirectory() as dossier:
        brut = os.path.join(dossier, "entree")
        wav = os.path.join(dossier, "sortie.wav")
        with open(brut, "wb") as f:
            f.write(await fichier.read())
        conv = subprocess.run(
            ["ffmpeg", "-y", "-i", brut, "-ac", "1", "-ar", "16000", wav],
            capture_output=True,
        )
        if conv.returncode != 0:
            return JSONResponse({"erreur": "Audio illisible."}, status_code=400)
        try:
            if moteur == "gemini":
                with open(wav, "rb") as f:
                    contenu = f.read()
                texte = await run_in_threadpool(transcrire_gemini, contenu)
            else:
                texte = transcrire_soloni(wav)
        except ErreurTranscription as e:
            return JSONResponse({"erreur": e.message, "detail": e.detail}, status_code=e.statut)
    return {"texte": texte, "moteur": moteur}
