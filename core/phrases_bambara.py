"""Page bambara : phrases proactives (22/11/2026, demande de Bourama).

La page parle d'elle même à six moments pour que la personne ne reste jamais devant le silence :
l'arrivée sur la page, une recherche web, une recherche de vidéos, une recherche d'images, la création
d'une image, et un outil qui prend du temps. Les textes vivent dans Supabase (table
bambara_phrases_proactives, migration 2026_11_22_page_bambara_phrases_proactives.sql) : on ajoute, on
change ou on retire une phrase sans toucher au code. Plusieurs phrases pour un même moment sont des
variantes, le frontend en tire une au hasard.

L'audio n'est pas fabriqué à chaque visite. Le serveur fait lire le texte par la voix du TTS (la même
variable que le reste de la page, VOIX_BAMBARA_VOIX) une seule fois et garde le fichier à côté du
texte. L'empreinte (voix et texte) dit avec quoi il a été fabriqué : si le texte ou la voix change,
l'audio est refait tout seul, en arrière plan, et la phrase n'est proposée de nouveau qu'une fois prête.

Ces phrases sont communes à tous les comptes : aucune donnée de compte, donc rien à ajouter à
core/purge_compte.py ni à l'export de api/profiles.py.

Les erreurs sont des codes stables traduits dans core/erreurs.py (français et anglais) et dans
lib/erreurs.ts côté frontend. Le frontend ne les montre jamais à l'écran : la page est faite pour
quelqu'un qui ne lit pas.
"""
import base64
import binascii
import hashlib
import io
import logging
import threading
import time
import uuid
import wave

from core.bambara_profils import ErreurBambara

MOMENTS = (
    "accueil",
    "recherche_web",
    "recherche_videos",
    "recherche_images",
    "creation_image",
    "outil_lent",
)

TABLE_PHRASES = "bambara_phrases_proactives"
TABLE_REGLAGES = "bambara_phrases_reglages"

# Valeurs de secours si la ligne des réglages est absente ou illisible (les mêmes que la migration).
DELAI_OUTIL_LENT_DEFAUT_S = 6
INTERVALLE_OUTIL_LENT_DEFAUT_S = 12
# Après un échec de fabrication, la même phrase n'est pas retentée avant ce délai.
DELAI_AVANT_NOUVEL_ESSAI_S = 60

_verrou = threading.Lock()
_en_fabrication: set[str] = set()
_derniers_echecs: dict[str, float] = {}


def empreinte(voix: str, texte: str) -> str:
    """Ce avec quoi un audio a été fabriqué : change dès que la voix ou le texte change."""
    return hashlib.sha256(f"{voix}\n{texte}".encode("utf-8")).hexdigest()[:32]


def _identifiant(valeur) -> str:
    try:
        return str(uuid.UUID(str(valeur)))
    except (ValueError, AttributeError, TypeError):
        raise ErreurBambara("BAMBARA_PHRASE_INTROUVABLE")


def _entier_borne(valeur, defaut: int, minimum: int, maximum: int) -> int:
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        return defaut
    return valeur if minimum <= valeur <= maximum else defaut


def lire_reglages(client) -> dict:
    """Les délais de la phrase « outil lent », ou leurs valeurs de secours."""
    reglages = {
        "delai_outil_lent_s": DELAI_OUTIL_LENT_DEFAUT_S,
        "intervalle_outil_lent_s": INTERVALLE_OUTIL_LENT_DEFAUT_S,
    }
    try:
        lignes = client.table(TABLE_REGLAGES).select("delai_outil_lent_s,intervalle_outil_lent_s").limit(1).execute().data
    except Exception as e:
        logging.error("ERREUR SUPABASE (réglages des phrases bambara) : %s", e)
        return reglages
    if lignes:
        reglages["delai_outil_lent_s"] = _entier_borne(lignes[0].get("delai_outil_lent_s"), DELAI_OUTIL_LENT_DEFAUT_S, 1, 120)
        reglages["intervalle_outil_lent_s"] = _entier_borne(
            lignes[0].get("intervalle_outil_lent_s"), INTERVALLE_OUTIL_LENT_DEFAUT_S, 3, 300
        )
    return reglages


def lister_phrases(client, voix: str):
    """
    Les phrases prêtes à jouer (audio fabriqué avec la voix et le texte actuels) et les identifiants de
    celles qui sont à fabriquer ou à refaire. L'audio lui même n'est pas renvoyé ici : il est lourd, le
    frontend le télécharge phrase par phrase (lire_audio).
    """
    try:
        lignes = (
            client.table(TABLE_PHRASES)
            .select("id,moment,texte,audio_duree_ms,audio_empreinte")
            .eq("actif", True)
            .execute()
            .data
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (liste des phrases bambara) : %s", e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    pretes, a_fabriquer = [], []
    for ligne in lignes or []:
        if ligne.get("moment") not in MOMENTS or not isinstance(ligne.get("texte"), str) or not ligne["texte"].strip():
            continue
        version = empreinte(voix, ligne["texte"])
        if ligne.get("audio_empreinte") == version:
            duree = ligne.get("audio_duree_ms")
            pretes.append(
                {"id": ligne["id"], "moment": ligne["moment"], "duree_ms": duree if isinstance(duree, int) else 0, "version": version}
            )
        else:
            a_fabriquer.append(ligne["id"])
    return {"reglages": lire_reglages(client), "phrases": pretes, "en_preparation": len(a_fabriquer)}, a_fabriquer


def lire_audio(client, phrase_id, voix: str) -> bytes:
    """Le fichier audio (WAV) d'une phrase prête. Introuvable tant qu'il n'est pas fabriqué avec la voix actuelle."""
    identifiant = _identifiant(phrase_id)
    try:
        lignes = (
            client.table(TABLE_PHRASES)
            .select("texte,audio_base64,audio_empreinte")
            .eq("id", identifiant)
            .eq("actif", True)
            .limit(1)
            .execute()
            .data
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (audio de la phrase bambara %s) : %s", identifiant, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    if not lignes:
        raise ErreurBambara("BAMBARA_PHRASE_INTROUVABLE")
    ligne = lignes[0]
    if not ligne.get("audio_base64") or ligne.get("audio_empreinte") != empreinte(voix, ligne.get("texte") or ""):
        raise ErreurBambara("BAMBARA_PHRASE_INTROUVABLE")
    try:
        return base64.b64decode(ligne["audio_base64"], validate=True)
    except (binascii.Error, ValueError):
        logging.error("Audio de la phrase bambara %s illisible, il sera refait", identifiant)
        raise ErreurBambara("BAMBARA_PHRASE_INTROUVABLE")


def duree_wav_ms(contenu: bytes) -> int:
    """Durée d'un fichier WAV en millisecondes, 0 si le fichier ne se lit pas."""
    try:
        with wave.open(io.BytesIO(contenu), "rb") as fichier:
            cadence = fichier.getframerate()
            return int(fichier.getnframes() * 1000 / cadence) if cadence else 0
    except (wave.Error, EOFError):
        return 0


def fabriquer_audios(client, voix: str, identifiants, synthetiser) -> int:
    """
    Fait lire par le TTS chaque phrase donnée et garde l'audio à côté du texte. `synthetiser(texte)` rend le
    WAV en octets. Une phrase qui échoue est passée (journal, nouvel essai plus tard) sans arrêter les autres.
    Une phrase déjà en cours de fabrication par un autre appel est laissée à celui ci. Rend le nombre de
    phrases fabriquées.
    """
    fabriquees = 0
    for identifiant in identifiants:
        with _verrou:
            if identifiant in _en_fabrication:
                continue
            if time.monotonic() - _derniers_echecs.get(identifiant, -DELAI_AVANT_NOUVEL_ESSAI_S) < DELAI_AVANT_NOUVEL_ESSAI_S:
                continue
            _en_fabrication.add(identifiant)
        try:
            lignes = client.table(TABLE_PHRASES).select("texte").eq("id", identifiant).eq("actif", True).limit(1).execute().data
            if not lignes:
                continue
            texte = lignes[0]["texte"]
            contenu = synthetiser(texte)
            if not contenu:
                raise ValueError("audio vide")
            # Le texte est redonné au filtre : s'il a changé pendant la fabrication, rien n'est écrit
            # (l'audio ne correspond plus) et la phrase sera refaite au prochain passage.
            client.table(TABLE_PHRASES).update(
                {
                    "audio_base64": base64.b64encode(contenu).decode("ascii"),
                    "audio_duree_ms": duree_wav_ms(contenu),
                    "audio_empreinte": empreinte(voix, texte),
                }
            ).eq("id", identifiant).eq("texte", texte).execute()
            _derniers_echecs.pop(identifiant, None)
            fabriquees += 1
        except Exception as e:
            _derniers_echecs[identifiant] = time.monotonic()
            logging.error("ERREUR (fabrication de l'audio de la phrase bambara %s) : %s", identifiant, e)
        finally:
            with _verrou:
                _en_fabrication.discard(identifiant)
    return fabriquees
