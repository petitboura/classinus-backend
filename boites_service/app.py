"""
Service de boîtes : l'API que le backend Classinus appelle pour créer, utiliser et détruire des
boîtes Docker isolées. C'est le seul composant qui touche au socket Docker.

Démarrage : uvicorn boites_service.app:app --host 0.0.0.0 --port 8080
Variables : BOITES_TOKEN (obligatoire) puis les limites décrites dans docker_cli.py.
"""
import asyncio
import hmac
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from boites_service import proxy as proxy_mod
from boites_service.docker_cli import Docker, ErreurDocker, chemin_sur, id_valide

registre = proxy_mod.RegistreBoites()
docker = Docker()


def _token_attendu() -> str:
    token = os.environ.get("BOITES_TOKEN", "")
    if not token:
        raise RuntimeError("BOITES_TOKEN est obligatoire : le service refuse de démarrer sans jeton.")
    return token


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _token_attendu()
    port = docker.port_proxy
    serveur = await asyncio.start_server(proxy_mod.fabriquer_gestionnaire(registre), "0.0.0.0", port)
    logging.info("proxy de sortie filtrée sur le port %s", port)
    balayage = asyncio.create_task(_balayer_navigateurs())
    try:
        yield
    finally:
        balayage.cancel()
        serveur.close()


def _fermer_navigateurs_perimes() -> int:
    """Détruit les boîtes navigateur plus vieilles que BOITES_NAV_DUREE_MAX secondes (jamais une boîte oubliée)."""
    limite = time.time() - int(os.environ.get("BOITES_NAV_DUREE_MAX", "900"))
    detruites = 0
    for boite_id, cree in docker.lister_navigateurs():
        if cree < limite:
            docker.supprimer(boite_id)
            registre.oublier(boite_id)
            detruites += 1
    return detruites


async def _balayer_navigateurs():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(_fermer_navigateurs_perimes)
        except Exception as e:
            logging.warning("balayage des boîtes navigateur : %s", type(e).__name__)


app = FastAPI(title="Classinus boîtes", lifespan=_lifespan)


def _authentifier(authorization: str = Header(default="")) -> None:
    attendu = _token_attendu()
    fourni = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(fourni.encode(), attendu.encode()):
        raise HTTPException(status_code=401, detail="jeton invalide")


@app.exception_handler(ErreurDocker)
async def _erreur_docker(_requete: Request, erreur: ErreurDocker):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=erreur.status, content={"detail": str(erreur)})


class CreationBoite(BaseModel):
    timeout: int = Field(default=3600, ge=60, le=86400)


class Commande(BaseModel):
    commande: str = Field(min_length=1, max_length=200_000)
    timeout: int = Field(default=60, ge=1, le=3600)


class Reseau(BaseModel):
    allow_out: list[str] = Field(default_factory=list, max_length=200)


class OuvertureNavigateur(BaseModel):
    cle: str = Field(min_length=16, max_length=32)
    utilisateur: str = Field(min_length=16, max_length=32)


def _existante(boite_id: str) -> str:
    etat = docker.etat(id_valide(boite_id))
    if etat is None:
        raise HTTPException(status_code=404, detail="not found")
    return etat


@app.get("/sante")
def sante():
    return {"ok": True}


@app.get("/boites", dependencies=[Depends(_authentifier)])
def lister():
    return {"boites": docker.lister()}


@app.post("/boites", dependencies=[Depends(_authentifier)])
def creer(_corps: CreationBoite):
    maximum = int(os.environ.get("BOITES_MAX", "20"))
    if len(docker.lister()) >= maximum:
        raise HTTPException(status_code=429, detail="capacité atteinte")
    boite_id = uuid.uuid4().hex
    docker.creer(boite_id)
    # Sans règle, la boîte n'a aucun accès au réseau : le proxy refuse toute adresse inconnue.
    registre.regler(boite_id, docker.adresse(boite_id), [])
    return {"id": boite_id}


@app.post("/navigateurs", dependencies=[Depends(_authentifier)])
def ouvrir_navigateur(corps: OuvertureNavigateur):
    """Boîte navigateur d'une conversation : créée si elle n'existe pas, reprise si elle est arrêtée.
    L'identifiant est calculé par le backend (empreinte de l'utilisateur et de la conversation) : aucune
    base de données n'est nécessaire pour la retrouver."""
    boite_id = id_valide(corps.cle)
    utilisateur = id_valide(corps.utilisateur)
    etat = docker.etat(boite_id)
    if etat is None:
        if len(docker.lister_navigateurs()) >= int(os.environ.get("BOITES_NAV_MAX", "3")):
            raise HTTPException(status_code=429, detail="capacité atteinte")
        if len(docker.lister()) >= int(os.environ.get("BOITES_MAX", "20")):
            raise HTTPException(status_code=429, detail="capacité atteinte")
        docker.creer(boite_id, navigateur=True, utilisateur=utilisateur)
    elif etat != "running":
        docker.demarrer(boite_id)
    # Réseau fermé tant que le backend n'a pas envoyé ses domaines autorisés (PUT /boites/{id}/reseau).
    registre.regler(boite_id, docker.adresse(boite_id), [])
    return {"id": boite_id}


@app.delete("/navigateurs", dependencies=[Depends(_authentifier)])
def detruire_navigateurs_utilisateur(utilisateur: str = Query(...)):
    """Détruit toutes les boîtes navigateur d'un utilisateur (suppression de compte)."""
    detruites = 0
    for boite_id, _cree in docker.lister_navigateurs(id_valide(utilisateur)):
        docker.supprimer(boite_id)
        registre.oublier(boite_id)
        detruites += 1
    return {"detruites": detruites}


@app.post("/boites/{boite_id}/connexion", dependencies=[Depends(_authentifier)])
def connecter(boite_id: str, _corps: CreationBoite | None = None):
    etat = _existante(boite_id)
    if etat != "running":
        docker.demarrer(boite_id)
    # Une adresse peut changer après une reprise : le réseau est donc réglé de nouveau par le backend.
    registre.regler(boite_id, docker.adresse(boite_id), [])
    return {"id": boite_id}


@app.post("/boites/{boite_id}/pause", dependencies=[Depends(_authentifier)])
def pause(boite_id: str):
    _existante(boite_id)
    docker.arreter(boite_id)
    registre.oublier(boite_id)
    return {"id": boite_id}


@app.delete("/boites/{boite_id}", dependencies=[Depends(_authentifier)])
def detruire(boite_id: str):
    id_valide(boite_id)
    docker.supprimer(boite_id)
    registre.oublier(boite_id)
    return {"id": boite_id}


@app.put("/boites/{boite_id}/reseau", dependencies=[Depends(_authentifier)])
def regler_reseau(boite_id: str, corps: Reseau):
    _existante(boite_id)
    registre.regler(boite_id, docker.adresse(boite_id), corps.allow_out)
    return {"id": boite_id, "domaines": len(corps.allow_out)}


@app.post("/boites/{boite_id}/commande", dependencies=[Depends(_authentifier)])
def commande(boite_id: str, corps: Commande):
    _existante(boite_id)
    return docker.executer(boite_id, corps.commande, corps.timeout)


@app.get("/boites/{boite_id}/fichier", dependencies=[Depends(_authentifier)])
def lire_fichier(boite_id: str, chemin: str = Query(...)):
    _existante(boite_id)
    return Response(content=docker.lire(boite_id, chemin_sur(chemin)), media_type="application/octet-stream")


@app.put("/boites/{boite_id}/fichier", dependencies=[Depends(_authentifier)])
async def ecrire_fichier(boite_id: str, requete: Request, chemin: str = Query(...)):
    _existante(boite_id)
    docker.ecrire(boite_id, chemin_sur(chemin), await requete.body())
    return {"id": boite_id}
