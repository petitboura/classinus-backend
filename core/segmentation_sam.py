"""
Segmentation SAM 3.1 (Meta Model API) : detourage d'un objet nomme en
texte dans une image, rendu en PNG sur fond transparent.

Flux : l'image publique est envoyee a POST /v1/responses (modele
sam-3.1, streaming). Le texte special renvoye est decode avec le
parseur officiel meta_sam_parser (aucune dependance), puis les masques
sont composes avec Pillow : seuls les pixels des objets trouves sont
gardes, tout le reste devient transparent. Le PNG final est televerse
au meme endroit que les images generees (voir generation_images.py).
"""

import io
import json
import logging
import os

import requests
from PIL import Image

from core.generation_images import _est_image_valide, _televerser_image
from core.securite_url import valider_url_externe

URL_BASE_META = "https://api.meta.ai/v1"
MODELE_SAM = "sam-3.1"


def sam_disponible() -> bool:
    return bool(os.environ.get("MODEL_API_KEY"))


def _telecharger_image(url: str) -> bytes:
    valider_url_externe(url)
    reponse = requests.get(url, timeout=30)
    reponse.raise_for_status()
    if not _est_image_valide(reponse.content):
        raise RuntimeError("Le fichier joint n'est pas une image lisible.")
    return reponse.content


def _demander_segmentation(image_url: str, consigne: str, cle: str) -> str:
    """Renvoie le texte brut de segmentation produit par SAM 3.1."""
    reponse = requests.post(
        f"{URL_BASE_META}/responses",
        headers={
            "Authorization": f"Bearer {cle}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json={
            "model": MODELE_SAM,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": consigne},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }
            ],
            "stream": True,
            "metadata": {"mask_encoding": "one_bit"},
        },
        timeout=180,
        stream=True,
    )
    reponse.raise_for_status()
    morceaux = []
    for ligne in reponse.iter_lines(decode_unicode=True):
        if not ligne or not ligne.startswith("data:"):
            continue
        donnees = ligne[5:].strip()
        if donnees == "[DONE]":
            break
        try:
            evenement = json.loads(donnees)
        except json.JSONDecodeError:
            continue
        if evenement.get("type") == "response.output_text.delta":
            delta = evenement.get("delta")
            if delta:
                morceaux.append(delta)
    texte = "".join(morceaux)
    if not texte.strip():
        raise RuntimeError("SAM n'a renvoye aucun resultat pour cette image.")
    return texte


def _composer_detourage(image_bytes: bytes, texte_segmentation: str) -> bytes:
    from meta_sam_parser import (
        CompletedOutcome,
        SegmentationMaskRecord,
        decode_mask_to_raster,
        image_segmentation_format,
    )

    parseur = image_segmentation_format().create_parser()
    parseur.push(texte_segmentation)
    resultat = parseur.finish(CompletedOutcome()).result
    masques = [r for r in resultat.records if isinstance(r, SegmentationMaskRecord)]
    if not masques:
        raise RuntimeError("Aucun objet correspondant a la consigne n'a ete trouve dans l'image.")

    originale = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    sortie = Image.new("RGBA", originale.size, (0, 0, 0, 0))
    for enregistrement in masques:
        bornes = enregistrement.bounds
        gauche, haut = int(round(bornes.left)), int(round(bornes.top))
        droite, bas = int(round(bornes.right)), int(round(bornes.bottom))
        largeur, hauteur = droite - gauche, bas - haut
        if largeur <= 0 or hauteur <= 0:
            continue
        raster = decode_mask_to_raster(enregistrement.mask)
        masque = Image.frombytes(
            "L",
            (enregistrement.mask.width, enregistrement.mask.height),
            bytes(255 if valeur else 0 for valeur in raster),
        )
        if masque.size != (largeur, hauteur):
            masque = masque.resize((largeur, hauteur), Image.NEAREST)
        zone = originale.crop((gauche, haut, droite, bas))
        sortie.paste(zone, (gauche, haut), masque)
    tampon = io.BytesIO()
    sortie.save(tampon, format="PNG")
    return tampon.getvalue()


def segmenter_et_detourer(image_url: str, consigne: str) -> str:
    """Detoure l'objet nomme par `consigne` et renvoie l'URL publique du PNG transparent."""
    cle = os.environ.get("MODEL_API_KEY")
    if not cle:
        raise RuntimeError("La segmentation SAM n'est pas configuree (MODEL_API_KEY absente).")
    consigne = (consigne or "").strip()
    if not consigne:
        raise RuntimeError("Precise l'objet a detourer, par exemple : la voiture rouge.")
    image_bytes = _telecharger_image(image_url)
    texte = _demander_segmentation(image_url, consigne, cle)
    png = _composer_detourage(image_bytes, texte)
    return _televerser_image(png, "image/png")
