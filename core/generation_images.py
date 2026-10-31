"""
Generation d'images, trois fournisseurs dans l'ordre de priorite :

1. Meta Model API (Muse Image, modele muse-image-1.0) : utilise
   uniquement si MODEL_API_KEY est configuree. C'est le fournisseur
   demande par Bourama le 31/10/2026 pour l'outil generer_image.
2. Together AI (Flux Schnell), environ 0,003 dollar par image :
   utilise si TOGETHER_API_KEY est configuree.
3. Pollinations.ai (https://pollinations.ai) : gratuit, sans cle,
   repli par defaut.

Si le fournisseur prioritaire echoue, les suivants sont essayes dans
l'ordre (l'echec est journalise) plutot que de laisser l'etudiant sans
image. L'outil n'est donc jamais totalement invisible pour l'agent.
"""

import base64
import logging
import os
import urllib.parse
import uuid

import requests

from api.auth import supabase
from core import stockage_r2

BUCKET = "generations"
MODELE_TOGETHER = "black-forest-labs/FLUX.1-schnell"
MODELE_META_IMAGE = "muse-image-1.0"
URL_BASE_META = "https://api.meta.ai/v1"

# CORRECTIF 2026-07-31 (audit sécurité/UX) : avant, tout ce qui revenait
# d'un fournisseur avec un statut HTTP 200 était uploadé et servi tel
# quel en forçant "image/png", sans jamais vérifier que c'était
# réellement une image. Si Pollinations/Together renvoie, avec un
# statut 200, une page d'erreur ou un message ("trop de requêtes",
# quota dépassé...) au lieu d'une vraie image, la personne se retrouvait
# avec une image cassée qui ne s'affiche pas, sans aucune explication --
# impossible pour elle de savoir si c'est sa consigne, un bug de l'app,
# ou le service externe qui a un souci.
#
# Vérification par signature binaire (magic bytes) plutôt que par
# l'en-tête Content-Type de la réponse HTTP : une page d'erreur HTML/
# JSON ne matchera jamais ces signatures, alors qu'un en-tête peut être
# absent ou trompeur (mal configuré côté fournisseur).
_SIGNATURES_IMAGE = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",  # JPEG
    b"GIF87a",
    b"GIF89a",
)


def _est_image_valide(donnees: bytes) -> bool:
    if not donnees or len(donnees) < 12:
        return False
    if donnees.startswith(_SIGNATURES_IMAGE):
        return True
    # WEBP : conteneur RIFF avec la sous-marque "WEBP" à l'offset 8
    if donnees[:4] == b"RIFF" and donnees[8:12] == b"WEBP":
        return True
    return False


def _get_secret(cle):
    return os.environ.get(cle)


def image_generation_disponible() -> bool:
    """
    Toujours True maintenant (Pollinations ne demande rien). Fonction
    conservée (plutôt que supprimée) pour ne pas casser les appels
    existants dans serveur_mcp_generation.py et api/generation.py --
    et parce que ça reste un point d'extension utile si jamais on
    voulait un jour un mode "désactivé de force".
    """
    return True


def _generer_via_meta(prompt: str, cle: str) -> bytes:
    reponse = requests.post(
        f"{URL_BASE_META}/images/generations",
        headers={"Authorization": f"Bearer {cle}", "Content-Type": "application/json"},
        json={"model": MODELE_META_IMAGE, "prompt": prompt, "n": 1, "output_format": "png"},
        timeout=180,
    )
    reponse.raise_for_status()
    donnees = reponse.json().get("data") or []
    if not donnees:
        raise RuntimeError("Meta Model API n'a renvoye aucune image.")
    premiere = donnees[0]
    if premiere.get("b64_json"):
        return base64.b64decode(premiere["b64_json"])
    if premiere.get("url"):
        telechargee = requests.get(premiere["url"], timeout=60)
        telechargee.raise_for_status()
        return telechargee.content
    raise RuntimeError("Reponse Meta Model API sans image exploitable.")


def _generer_via_pollinations(prompt: str) -> bytes:
    prompt_encode = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{prompt_encode}?width=1024&height=1024&nologo=true"
    reponse = requests.get(url, timeout=60)
    reponse.raise_for_status()
    return reponse.content


def _generer_via_together(prompt: str, cle: str) -> bytes:
    reponse = requests.post(
        "https://api.together.xyz/v1/images/generations",
        headers={"Authorization": f"Bearer {cle}"},
        json={"model": MODELE_TOGETHER, "prompt": prompt, "n": 1, "width": 1024, "height": 1024},
        timeout=60,
    )
    reponse.raise_for_status()
    url_image_temporaire = reponse.json()["data"][0]["url"]
    return requests.get(url_image_temporaire, timeout=30).content


def _televerser_image(image_bytes: bytes, type_contenu: str = "image/png") -> str:
    chemin = f"images/{uuid.uuid4()}.png"
    try:
        stockage_r2.from_(BUCKET).upload(chemin, image_bytes, {"content-type": type_contenu})
    except Exception as e:
        logging.error(f"ERREUR SUPABASE STORAGE (upload image {chemin}) : {e}")
        raise
    return stockage_r2.from_(BUCKET).get_public_url(chemin)


def generer_image(prompt: str) -> str:
    """
    Ordre essaye : Meta Model API si MODEL_API_KEY est configuree,
    puis Together AI si sa cle est presente, puis Pollinations.
    Televerse le resultat et renvoie son URL publique.
    """
    fournisseurs = []
    cle_meta = _get_secret("MODEL_API_KEY")
    if cle_meta:
        fournisseurs.append(("Meta Muse Image", lambda: _generer_via_meta(prompt, cle_meta)))
    cle_together = _get_secret("TOGETHER_API_KEY")
    if cle_together:
        fournisseurs.append(("Together AI", lambda: _generer_via_together(prompt, cle_together)))
    fournisseurs.append(("Pollinations", lambda: _generer_via_pollinations(prompt)))

    image_bytes = None
    derniere_erreur = None
    for nom, generer in fournisseurs:
        try:
            image_bytes = generer()
            break
        except Exception as e:
            derniere_erreur = e
            logging.error(f"ERREUR GENERATION IMAGE ({nom}) : {e}")
    if image_bytes is None:
        raise RuntimeError(f"La generation d'image a echoue chez tous les fournisseurs : {derniere_erreur}")

    if not _est_image_valide(image_bytes):
        # Le fournisseur a répondu avec un statut "succès" mais le contenu
        # n'est pas une image reconnue (page d'erreur, message de quota
        # dépassé...) -- on le signale clairement plutôt que d'uploader
        # une image cassée que la personne ne pourra jamais afficher.
        apercu = image_bytes[:200].decode("utf-8", errors="replace") if image_bytes else "(vide)"
        logging.error(f"ERREUR GENERATION IMAGE : réponse reçue n'est pas une image valide. Aperçu : {apercu!r}")
        raise RuntimeError(
            "Le service de génération d'image a renvoyé un contenu invalide (pas une image) -- réessaie dans un instant."
        )

    return _televerser_image(image_bytes, "image/png")

