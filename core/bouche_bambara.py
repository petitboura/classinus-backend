"""Bouche bambara : synthèse vocale de test pour les voix candidates (12/11/2026).

Demande de Bourama : installer d'abord les « bouches » (texte vers voix) pour juger
à l'oreille laquelle est la meilleure, avant de brancher quoi que ce soit dans Classinus.

Ce module ne dépend ni de Supabase ni du backend principal. Il est chargé par le service
séparé api/main_bouche.py (Dockerfile.bouche) et par les tests. PyTorch et Transformers
sont importés seulement au premier chargement d'une voix, jamais à l'import du module.

Le catalogue des voix est une simple table : ajouter une voix, c'est ajouter une entrée
dans VOIX, rien d'autre. Les voix actives viennent de la variable BOUCHE_VOIX_ACTIVES
(liste d'identifiants séparés par des virgules, toutes si elle est absente).
"""
from __future__ import annotations

import io
import logging
import os
import threading
import wave

logger = logging.getLogger(__name__)

# Statut de licence, tel que lu sur la fiche du modèle (pas une décision juridique) :
#   "non_commercial" : la fiche interdit l'usage commercial, test seulement.
#   "a_verifier"     : la fiche ne dit rien de clair, à confirmer avant toute production.
VOIX: dict[str, dict] = {
    "bam_vits": {
        "nom": "Bam VITS (RobotsMali)",
        "depot": "RobotsMali/bam-vits",
        "locuteurs": 20,
        # Les données d'entraînement ont été mises en minuscules (fiche du modèle).
        "minuscules": True,
        "licence": "a_verifier",
        # Fiche du modèle : point de contrôle de recherche, très peu entraîné.
        "experimental": True,
    },
    "mms_sudoping01": {
        "nom": "MMS Bambara (sudoping01)",
        "depot": "sudoping01/bambara-tts",
        "locuteurs": 1,
        "minuscules": False,
        "licence": "non_commercial",
        # Licence CC BY-NC 4.0 sur la fiche : usage non commercial seulement.
        "experimental": False,
    },
}

TEXTE_MAX_DEFAUT = 600
SYNTHESES_MAX_DEFAUT = 1


class BoucheErreur(Exception):
    """Erreur prévue, avec un code stable de core/erreurs.py."""

    def __init__(self, statut: int, code: str):
        super().__init__(code)
        self.statut = statut
        self.code = code


def _entier_env(nom: str, defaut: int) -> int:
    try:
        valeur = int((os.environ.get(nom) or "").strip())
    except ValueError:
        return defaut
    return valeur if valeur > 0 else defaut


def texte_max() -> int:
    return _entier_env("BOUCHE_TEXTE_MAX", TEXTE_MAX_DEFAUT)


def voix_actives() -> list[str]:
    brut = (os.environ.get("BOUCHE_VOIX_ACTIVES") or "").strip()
    if not brut:
        return list(VOIX)
    demandees = [v.strip() for v in brut.split(",") if v.strip()]
    return [v for v in demandees if v in VOIX]


def lister_voix() -> list[dict]:
    """Description des voix actives, pour la page de test.

    Aucun texte lisible n'est renvoyé : l'écran écrit lui-même les libellés, en français et en anglais.
    """
    return [
        {
            "id": voix_id,
            "nom": VOIX[voix_id]["nom"],
            "depot": VOIX[voix_id]["depot"],
            "locuteurs": VOIX[voix_id]["locuteurs"],
            "licence": VOIX[voix_id]["licence"],
            "experimental": VOIX[voix_id]["experimental"],
        }
        for voix_id in voix_actives()
    ]


def valider_demande(voix_id: str, texte: str, locuteur: int) -> tuple[str, int]:
    """Vérifie la demande et renvoie (texte nettoyé, locuteur). Lève BoucheErreur sinon."""
    if voix_id not in VOIX or voix_id not in voix_actives():
        raise BoucheErreur(404, "BOUCHE_VOIX_INCONNUE")
    propre = (texte or "").strip()
    if not propre:
        raise BoucheErreur(400, "BOUCHE_TEXTE_VIDE")
    if len(propre) > texte_max():
        raise BoucheErreur(400, "BOUCHE_TEXTE_TROP_LONG")
    if not 0 <= locuteur < VOIX[voix_id]["locuteurs"]:
        raise BoucheErreur(400, "BOUCHE_LOCUTEUR_INVALIDE")
    return propre, locuteur


_verrou_chargement = threading.Lock()
_cache: dict[str, tuple] = {}
_places = threading.BoundedSemaphore(_entier_env("BOUCHE_SYNTHESES_MAX", SYNTHESES_MAX_DEFAUT))


def _charger(voix_id: str) -> tuple:
    """Charge le modèle une seule fois, au premier appel de cette voix."""
    with _verrou_chargement:
        if voix_id in _cache:
            return _cache[voix_id]
        try:
            from transformers import AutoTokenizer, VitsModel

            depot = VOIX[voix_id]["depot"]
            tokenizer = AutoTokenizer.from_pretrained(depot)
            modele = VitsModel.from_pretrained(depot)
            modele.eval()
        except Exception:
            logger.exception("Chargement de la voix %s impossible", voix_id)
            raise BoucheErreur(503, "BOUCHE_INDISPONIBLE")
        _cache[voix_id] = (tokenizer, modele)
        return _cache[voix_id]


def encoder_wav(echantillons, frequence: int) -> bytes:
    """Transforme un signal flottant (entre -1 et 1) en fichier WAV 16 bits mono."""
    import numpy as np

    signal = np.asarray(echantillons, dtype="float32").reshape(-1)
    signal = np.clip(signal, -1.0, 1.0)
    entiers = (signal * 32767.0).astype("<i2")
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(2)
        fichier.setframerate(int(frequence))
        fichier.writeframes(entiers.tobytes())
    return tampon.getvalue()


def synthetiser(voix_id: str, texte: str, locuteur: int = 0) -> bytes:
    """Texte bambara vers fichier WAV. Bloque jusqu'à une place libre (un calcul à la fois par défaut)."""
    propre, locuteur = valider_demande(voix_id, texte, locuteur)
    if VOIX[voix_id]["minuscules"]:
        propre = propre.lower()
    tokenizer, modele = _charger(voix_id)
    with _places:
        try:
            import torch

            entrees = tokenizer(propre, return_tensors="pt")
            arguments = {"speaker_id": locuteur} if VOIX[voix_id]["locuteurs"] > 1 else {}
            with torch.inference_mode():
                sortie = modele(**entrees, **arguments).waveform
            return encoder_wav(sortie.squeeze().cpu().numpy(), modele.config.sampling_rate)
        except BoucheErreur:
            raise
        except Exception:
            logger.exception("Synthèse échouée avec la voix %s", voix_id)
            raise BoucheErreur(500, "BOUCHE_SYNTHESE_ECHEC")
