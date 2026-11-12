"""Catalogue et synthèse des voix bambara de test (dossier isolé bambara-bouche).

Aucune dépendance au reste du backend. PyTorch et Transformers ne sont importés qu'au
chargement d'une voix, jamais à l'import du module (les tests tournent sans eux).

Ajouter une voix : ajouter une entrée dans VOIX. Les voix actives viennent de la variable
VOIX_ACTIVES (identifiants séparés par des virgules), toutes si elle est absente.
"""
from __future__ import annotations

import io
import logging
import os
import threading
import traceback
import wave

logger = logging.getLogger(__name__)

# Statut de licence tel que lu sur la fiche du modèle (pas un avis juridique) :
#   "non_commercial" : la fiche interdit l'usage commercial, test seulement.
#   "a_verifier"     : la fiche ne dit rien de clair, à confirmer avant toute production.
VOIX: dict[str, dict] = {
    "bam_vits": {
        "nom": "Bam VITS (RobotsMali)",
        "depot": "RobotsMali/bam-vits",
        "locuteurs": 20,
        # Fiche du modèle : les textes d'entraînement étaient en minuscules.
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
        # Fiche du modèle : CC BY-NC 4.0, usage non commercial seulement.
        "licence": "non_commercial",
        "experimental": False,
    },
}

TEXTE_MAX_DEFAUT = 600
# Hasard ajouté à chaque synthèse par VITS (défaut du modèle : 0.667 et 0.8). Les voix peu
# entraînées le transforment en bruit audible : on le baisse, réglable sans toucher au code.
BRUIT_DEFAUT = 0.3
BRUIT_DUREE_DEFAUT = 0.8


class ErreurVoix(Exception):
    """Erreur prévue, avec un statut HTTP et un message lisible en français."""

    def __init__(self, statut: int, message: str, detail: str | None = None):
        super().__init__(message)
        self.statut = statut
        self.message = message
        self.detail = detail


def _entier_env(nom: str, defaut: int) -> int:
    try:
        valeur = int((os.environ.get(nom) or "").strip())
    except ValueError:
        return defaut
    return valeur if valeur > 0 else defaut


def _flottant_env(nom: str, defaut: float) -> float:
    """Lit un nombre entre 0 et 1 dans l'environnement; valeur absente ou invalide : défaut."""
    try:
        valeur = float((os.environ.get(nom) or "").strip())
    except ValueError:
        return defaut
    return valeur if 0.0 <= valeur <= 1.0 else defaut


def bruit_scale() -> float:
    return _flottant_env("BRUIT_SCALE", BRUIT_DEFAUT)


def bruit_duree() -> float:
    return _flottant_env("BRUIT_DUREE", BRUIT_DUREE_DEFAUT)


def texte_max() -> int:
    return _entier_env("TEXTE_MAX", TEXTE_MAX_DEFAUT)


def voix_actives() -> list[str]:
    brut = (os.environ.get("VOIX_ACTIVES") or "").strip()
    if not brut:
        return list(VOIX)
    return [v for v in (s.strip() for s in brut.split(",")) if v in VOIX]


def lister_voix() -> list[dict]:
    return [{"id": i, **{k: VOIX[i][k] for k in ("nom", "depot", "locuteurs", "licence", "experimental")}} for i in voix_actives()]


# Chargement des modèles : un état par voix, lisible par la page pendant le téléchargement.
_etat: dict[str, dict] = {i: {"pret": False, "chargement": False, "erreur": None} for i in VOIX}
_modeles: dict[str, tuple] = {}
_verrou = threading.Lock()
_places = threading.BoundedSemaphore(_entier_env("SYNTHESES_MAX", 1))


def etat_voix() -> dict:
    return {i: dict(_etat[i]) for i in voix_actives()}


def charger(voix_id: str) -> None:
    """Charge une voix (une seule fois). Ne lève jamais : l'échec est gardé dans l'état."""
    with _verrou:
        etat = _etat[voix_id]
        if etat["pret"] or etat["chargement"]:
            return
        etat.update(chargement=True, erreur=None)
    try:
        from transformers import AutoTokenizer, VitsModel

        depot = VOIX[voix_id]["depot"]
        tokenizer = AutoTokenizer.from_pretrained(depot)
        modele, infos = VitsModel.from_pretrained(depot, output_loading_info=True)
        # Poids absents du fichier de voix : ils restent au hasard et donnent un bourdonnement.
        manquantes = sorted(infos.get("missing_keys", []))
        if manquantes:
            logger.warning("Voix %s : %d poids non chargés : %s", voix_id, len(manquantes), manquantes[:20])
        _etat[voix_id]["manquantes"] = manquantes[:20]
        _etat[voix_id]["nb_manquantes"] = len(manquantes)
        modele.eval()
        modele.noise_scale = bruit_scale()
        modele.noise_scale_duration = bruit_duree()
        _modeles[voix_id] = (tokenizer, modele)
        _etat[voix_id].update(pret=True, chargement=False)
    except Exception as e:
        logger.exception("Chargement de la voix %s impossible", voix_id)
        _etat[voix_id].update(pret=False, chargement=False, erreur=f"{type(e).__name__}: {e}")


def valider(voix_id: str, texte: str, locuteur: int) -> tuple[str, int]:
    if voix_id not in VOIX or voix_id not in voix_actives():
        raise ErreurVoix(404, "Cette voix n'existe pas ou n'est pas activée.")
    propre = (texte or "").strip()
    if not propre:
        raise ErreurVoix(400, "Écris un texte à faire lire.")
    if len(propre) > texte_max():
        raise ErreurVoix(400, f"Texte trop long : {texte_max()} caractères au maximum.")
    if not 0 <= locuteur < VOIX[voix_id]["locuteurs"]:
        raise ErreurVoix(400, "Ce locuteur n'existe pas pour cette voix.")
    return propre, locuteur


def encoder_wav(echantillons, frequence: int) -> bytes:
    """Signal flottant (entre -1 et 1) vers un fichier WAV 16 bits mono."""
    import numpy as np

    signal = np.clip(np.asarray(echantillons, dtype="float32").reshape(-1), -1.0, 1.0)
    entiers = (signal * 32767.0).astype("<i2")
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as fichier:
        fichier.setnchannels(1)
        fichier.setsampwidth(2)
        fichier.setframerate(int(frequence))
        fichier.writeframes(entiers.tobytes())
    return tampon.getvalue()


def synthetiser(voix_id: str, texte: str, locuteur: int = 0) -> bytes:
    propre, locuteur = valider(voix_id, texte, locuteur)
    etat = _etat[voix_id]
    if not etat["pret"]:
        if etat["erreur"]:
            raise ErreurVoix(500, "Cette voix n'a pas pu se charger.", etat["erreur"])
        if not etat["chargement"]:
            charger(voix_id)  # préchargement désactivé : chargement au premier usage
            if not etat["pret"]:
                raise ErreurVoix(500, "Cette voix n'a pas pu se charger.", etat["erreur"])
        else:
            raise ErreurVoix(503, "La voix charge encore, réessaie dans une minute.")
    if VOIX[voix_id]["minuscules"]:
        propre = propre.lower()
    tokenizer, modele = _modeles[voix_id]
    with _places:
        try:
            import torch

            entrees = tokenizer(propre, return_tensors="pt")
            arguments = {"speaker_id": locuteur} if VOIX[voix_id]["locuteurs"] > 1 else {}
            with torch.inference_mode():
                sortie = modele(**entrees, **arguments).waveform
            return encoder_wav(sortie.squeeze().cpu().numpy(), modele.config.sampling_rate)
        except Exception as e:
            trace = traceback.format_exc()
            logger.error("Synthèse échouée avec la voix %s\n%s", voix_id, trace)
            raise ErreurVoix(500, "La voix n'a pas réussi à lire ce texte : " + str(e), trace)
