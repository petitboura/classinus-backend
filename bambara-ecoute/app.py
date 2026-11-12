import os
import subprocess
import tempfile
import threading

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

MODEL_NAME = os.environ.get("MODEL_NAME", "RobotsMali/soloni-114m-tdt-ctc-v3")

app = FastAPI()
etat = {"modele": None, "pret": False, "erreur": None}


def charger_modele():
    try:
        import nemo.collections.asr as nemo_asr
        etat["modele"] = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.from_pretrained(model_name=MODEL_NAME)
        etat["pret"] = True
    except Exception as e:
        etat["erreur"] = str(e)


threading.Thread(target=charger_modele, daemon=True).start()


@app.get("/")
def accueil():
    return FileResponse("index.html")


@app.get("/etat")
def etat_modele():
    return {"pret": etat["pret"], "erreur": etat["erreur"], "modele": MODEL_NAME}


@app.post("/transcrire")
async def transcrire(fichier: UploadFile = File(...)):
    if not etat["pret"]:
        return JSONResponse({"erreur": "Le modèle charge encore, réessaie dans une minute."}, status_code=503)
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
            resultat = etat["modele"].transcribe([wav])
            if isinstance(resultat, tuple):
                resultat = resultat[0]
            premier = resultat[0]
            texte = premier.text if hasattr(premier, "text") else str(premier)
        except Exception as e:
            return JSONResponse({"erreur": "Échec de la transcription : " + str(e)}, status_code=500)
    return {"texte": texte}
