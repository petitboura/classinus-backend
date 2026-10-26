"""
Modification d'un zip existant sans tout réécrire (26/10/2026, demande
de Bourama). Le serveur ouvre le zip, retire, déplace ou ajoute les
fichiers demandés, puis enregistre un nouveau zip. L'IA ne relit ni ne
réécrit le contenu des fichiers qu'elle ne touche pas.

Un zip de départ est soit un zip déjà généré par Classinus (URL), soit
un zip joint au chat (référence donnée dans le sommaire du zip).
Les fichiers ajoutés viennent d'une URL, d'un texte, ou d'un fichier
d'un zip joint au chat (référence "job::index").
"""
import io
import logging
import uuid
import zipfile
from urllib.parse import unquote

import requests

from core import stockage_r2, zip_chat
from core.generation_archives import BUCKET
from core.securite_chemins import chemin_relatif_sur

TAILLE_MAX_OCTETS = 100 * 1024 * 1024


def _telecharger(url: str) -> bytes:
    """Fichier de notre propre stockage lu directement, sinon téléchargé comme generer_bundle."""
    prefixe = stockage_r2.from_(BUCKET).get_public_url("")
    if url.startswith(prefixe):
        return stockage_r2.from_(BUCKET).download(unquote(url[len(prefixe):].split("?", 1)[0]))
    reponse = requests.get(url, timeout=30)
    reponse.raise_for_status()
    return reponse.content


def _charger_zip(source: str) -> dict[str, bytes]:
    source = (source or "").strip()
    if source.startswith("http"):
        brut = _telecharger(source)
    else:
        job = zip_chat.obtenir_etat(source.split("::", 1)[0])
        brut = (job or {}).get("contenu_zip")
        if brut is None:
            raise ValueError("Zip de départ introuvable (zip du chat expiré ou trop gros, ou adresse invalide).")
    if len(brut) > TAILLE_MAX_OCTETS:
        raise ValueError("Zip de départ trop gros pour être modifié.")
    membres: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(brut)) as archive:
        for info in archive.infolist():
            if not info.is_dir():
                membres[chemin_relatif_sur(info.filename)] = archive.read(info)
    return membres


def _concerne(chemin: str, cible: str) -> bool:
    return chemin == cible or chemin.startswith(cible.rstrip("/") + "/")


def modifier_zip(nom_projet: str, zip_de_depart: str, elements: list | None, retirer: list | None, deplacer: dict | None) -> tuple[str, list[str]]:
    membres = _charger_zip(zip_de_depart)
    notes: list[str] = []

    for cible in retirer or []:
        cible = chemin_relatif_sur(cible)
        trouves = [c for c in membres if _concerne(c, cible)]
        for c in trouves:
            del membres[c]
        notes.append(f"Retiré : {cible} ({len(trouves)} fichier(s))" if trouves else f"Introuvable, rien retiré : {cible}")

    for ancien, nouveau in (deplacer or {}).items():
        ancien, nouveau = chemin_relatif_sur(ancien), chemin_relatif_sur(nouveau)
        trouves = [c for c in membres if _concerne(c, ancien)]
        for c in trouves:
            membres[nouveau + c[len(ancien):]] = membres.pop(c)
        notes.append(f"Déplacé : {ancien} vers {nouveau} ({len(trouves)} fichier(s))" if trouves else f"Introuvable, rien déplacé : {ancien}")

    for element in elements or []:
        chemin = chemin_relatif_sur(element["chemin"])
        if "url" in element:
            membres[chemin] = _telecharger(element["url"])
        elif "reference" in element:
            texte = zip_chat.lire_element(element["reference"])
            if texte is None:
                raise ValueError(f"Fichier de zip introuvable : {element['reference']}")
            membres[chemin] = texte.encode("utf-8")
        else:
            contenu = element["contenu"]
            membres[chemin] = contenu.encode("utf-8") if isinstance(contenu, str) else contenu
        notes.append(f"Ajouté : {chemin}")

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for chemin, contenu in membres.items():
            archive.writestr(chemin, contenu)
    stockage = f"bundles/{uuid.uuid4()}-{chemin_relatif_sur(nom_projet, 'archive')}.zip"
    try:
        stockage_r2.from_(BUCKET).upload(stockage, tampon.getvalue(), {"content-type": "application/zip"})
    except Exception as e:
        logging.error(f"ERREUR STOCKAGE (upload zip modifié {stockage}) : {e}")
        raise
    return stockage_r2.from_(BUCKET).get_public_url(stockage), notes
