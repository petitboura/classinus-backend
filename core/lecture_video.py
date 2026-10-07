"""
Lecture du contenu d'une vidéo YouTube (ce qui est dit dedans) pour Classinus.

Sert l'outil lire_video (core/outils_lecture_video.py). Complète
rechercher_video : la recherche trouve les vidéos, la lecture permet de
répondre à des questions sur leur contenu, de les résumer ou d'en citer un
passage.

Deux niveaux, essayés dans cet ordre :

1. Sous-titres de la vidéo (bibliothèque youtube-transcript-api), manuels
   ou automatiques, en préférant le français puis l'anglais, sinon la
   première langue disponible. Le texte est découpé avec un repère [m:ss]
   toutes les minutes environ, pour que le modèle puisse situer un passage.
2. Si les sous-titres sont inaccessibles (désactivés par l'auteur, vidéo
   privée, lecture bloquée par YouTube depuis nos serveurs...), la fiche de
   la vidéo (titre, chaîne, description) via le service officiel de
   YouTube, clairement présentée comme un contenu partiel.

Une vidéo longue est lue par tranches : la réponse indique à quelle minute
reprendre pour lire la suite (paramètre a_partir_de_minute).

Le retour est toujours un texte destiné au modèle, jamais une exception :
une vidéo illisible n'est pas une erreur de l'application, le modèle doit
simplement le dire à l'étudiant sans inventer.

Réglages par variables d'environnement :
- LECTURE_VIDEO_LONGUEUR_MAX : caractères lus par tranche (20000 par défaut)
- LECTURE_VIDEO_MEMOIRE_SECONDES : durée de mémorisation d'une vidéo lue
  (3600 par défaut)
- LECTURE_VIDEO_MEMOIRE_TAILLE : nombre de vidéos gardées (30 par défaut)
- YOUTUBE_API_KEY (sinon GOOGLE_API_KEY) : pour la fiche de secours

NON TESTÉ EN CONDITIONS RÉELLES au moment de l'écriture (07/10/2026) : à
vérifier en production au premier vrai essai. Point de vigilance connu :
YouTube bloque parfois les adresses des hébergeurs (type Railway) pour la
lecture des sous-titres, d'où le repli sur la fiche.
"""

import html
import logging
import os
import re
import threading
import time

import requests

from core.recherche_video import _masquer_cle

_URL_YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
_REGEX_ID_VIDEO = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|embed/|live/))([\w-]{11})"
)
_REGEX_ID_SEUL = re.compile(r"^[\w-]{11}$")
_INTERVALLE_REPERE_SECONDES = 60
_LONGUEUR_DESCRIPTION_MAX = 3000

_verrou = threading.Lock()
_memoire = {}  # id_video -> (instant, infos des sous-titres)


def _entier_env(nom, defaut):
    try:
        return int(os.environ.get(nom, defaut))
    except (TypeError, ValueError):
        return defaut


def extraire_id_video(texte):
    """Accepte une adresse YouTube ou directement l'identifiant à 11 caractères."""
    texte = (texte or "").strip()
    correspondance = _REGEX_ID_VIDEO.search(texte)
    if correspondance:
        return correspondance.group(1)
    if _REGEX_ID_SEUL.match(texte):
        return texte
    return None


def _formater_minute(secondes):
    secondes = int(secondes)
    heures, reste = divmod(secondes, 3600)
    minutes, secs = divmod(reste, 60)
    if heures:
        return f"{heures}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _raison_lisible(erreur):
    """Traduit une erreur technique en raison compréhensible, sans jargon."""
    nom = type(erreur).__name__
    if "Blocked" in nom:
        return "YouTube bloque la lecture des sous-titres depuis nos serveurs"
    if nom == "TranscriptsDisabled":
        return "l'auteur de la vidéo a désactivé les sous-titres"
    if nom in ("NoTranscriptFound", "StopIteration"):
        return "la vidéo n'a aucun sous-titre disponible"
    if nom in ("VideoUnavailable", "VideoUnplayable", "InvalidVideoId"):
        return "la vidéo est indisponible, privée ou supprimée"
    if nom == "AgeRestricted":
        return "la vidéo est réservée aux personnes majeures"
    return "la lecture des sous-titres a échoué"


def _lire_memoire(id_video):
    duree = _entier_env("LECTURE_VIDEO_MEMOIRE_SECONDES", 3600)
    with _verrou:
        entree = _memoire.get(id_video)
        if not entree:
            return None
        instant, infos = entree
        if time.time() - instant > duree:
            _memoire.pop(id_video, None)
            return None
        return infos


def _ecrire_memoire(id_video, infos):
    taille_max = _entier_env("LECTURE_VIDEO_MEMOIRE_TAILLE", 30)
    with _verrou:
        if len(_memoire) >= taille_max and id_video not in _memoire:
            plus_ancienne = min(_memoire, key=lambda k: _memoire[k][0])
            _memoire.pop(plus_ancienne, None)
        _memoire[id_video] = (time.time(), infos)


def _recuperer_sous_titres(id_video):
    """
    Renvoie {"langue", "automatique", "morceaux": [(secondes, texte), ...]}.
    Lève une exception si les sous-titres sont inaccessibles.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    liste = YouTubeTranscriptApi().list(id_video)
    try:
        transcription = liste.find_transcript(["fr", "en"])
    except Exception:
        transcription = next(iter(liste))  # première langue disponible

    morceaux = []
    for segment in transcription.fetch():
        texte = " ".join(html.unescape(segment.text).split())
        if texte:
            morceaux.append((float(segment.start), texte))
    if not morceaux:
        raise ValueError("sous-titres vides")
    return {
        "langue": transcription.language_code,
        "automatique": bool(transcription.is_generated),
        "morceaux": morceaux,
    }


def _recuperer_fiche(id_video):
    """Titre, chaîne et description via le service officiel de YouTube (1 point)."""
    cle = os.environ.get("YOUTUBE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not cle:
        return None
    try:
        reponse = requests.get(
            _URL_YOUTUBE_VIDEOS,
            params={"key": cle, "part": "snippet", "id": id_video},
            timeout=15,
        )
        reponse.raise_for_status()
        elements = reponse.json().get("items", [])
        if not elements:
            return None
        extrait = elements[0].get("snippet") or {}
        return {
            "titre": html.unescape(extrait.get("title") or ""),
            "chaine": html.unescape(extrait.get("channelTitle") or ""),
            "description": (extrait.get("description") or "")[:_LONGUEUR_DESCRIPTION_MAX],
        }
    except Exception as e:
        logging.warning(f"LECTURE VIDEO : fiche indisponible pour {id_video} ({_masquer_cle(e)}).")
        return None


def _construire_tranche(id_video, infos, a_partir_de_minute):
    morceaux = infos["morceaux"]
    longueur_max = _entier_env("LECTURE_VIDEO_LONGUEUR_MAX", 20000)
    debut_secondes = max(0, a_partir_de_minute) * 60

    lignes = []
    longueur = 0
    prochain_repere = None
    fin_secondes = None
    for secondes, texte in morceaux:
        if secondes < debut_secondes:
            continue
        if longueur >= longueur_max:
            fin_secondes = secondes
            break
        if prochain_repere is None or secondes >= prochain_repere:
            lignes.append(f"\n[{_formater_minute(secondes)}] ")
            prochain_repere = secondes + _INTERVALLE_REPERE_SECONDES
            longueur += 8
        lignes.append(texte + " ")
        longueur += len(texte) + 1

    texte_tranche = "".join(lignes).strip()
    duree_totale = morceaux[-1][0]

    entete = (
        f"Contenu parlé de la vidéo https://www.youtube.com/watch?v={id_video} "
        f"(sous-titres {'automatiques' if infos['automatique'] else 'manuels'}, langue : {infos['langue']}, "
        f"durée environ {_formater_minute(duree_totale)}). "
        f"Les repères [m:ss] indiquent le moment dans la vidéo. "
    )
    if fin_secondes is not None:
        minute_suite = int(fin_secondes // 60)
        entete += (
            f"Cette tranche s'arrête à la minute {minute_suite} : pour lire la suite, rappelle lire_video "
            f"avec a_partir_de_minute={minute_suite}. "
        )
    else:
        entete += "Cette tranche va jusqu'à la fin de la vidéo. "
    entete += "Base-toi uniquement sur ce texte, sans rien inventer au delà."
    return f"{entete}\n\n{texte_tranche}"


def lire_contenu_video(url_ou_id, a_partir_de_minute=0):
    """
    Renvoie un texte pour le modèle : le contenu parlé de la vidéo (par
    tranche), ou à défaut sa fiche, ou à défaut une explication claire de
    l'impossibilité. Ne lève jamais d'exception.
    """
    id_video = extraire_id_video(url_ou_id)
    if not id_video:
        return "Lien non reconnu : donne l'adresse complète d'une vidéo YouTube."

    try:
        a_partir_de_minute = int(a_partir_de_minute or 0)
    except (TypeError, ValueError):
        a_partir_de_minute = 0

    infos = _lire_memoire(id_video)
    raison = None
    if infos is None:
        try:
            infos = _recuperer_sous_titres(id_video)
            _ecrire_memoire(id_video, infos)
        except Exception as e:
            raison = _raison_lisible(e)
            logging.error(f"ERREUR LECTURE VIDEO ({id_video}) : {type(e).__name__} {_masquer_cle(str(e))[:200]}")

    if infos is not None:
        if a_partir_de_minute * 60 > infos["morceaux"][-1][0]:
            return (
                f"La vidéo dure environ {_formater_minute(infos['morceaux'][-1][0])} : "
                f"la minute {a_partir_de_minute} est après la fin."
            )
        return _construire_tranche(id_video, infos, a_partir_de_minute)

    fiche = _recuperer_fiche(id_video)
    message = f"Impossible de lire ce qui est dit dans cette vidéo : {raison}. "
    if fiche and (fiche["titre"] or fiche["description"]):
        message += (
            "Voici seulement sa fiche, qui ne remplace pas son contenu. "
            f"Titre : {fiche['titre']}. Chaîne : {fiche['chaine']}. Description : {fiche['description']} "
        )
    message += (
        "Dis-le clairement à l'étudiant : ne devine ni ne résume ce qui est dit dans la vidéo, "
        "et propose-lui de coller ici le passage qui l'intéresse."
    )
    return message
