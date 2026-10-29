"""Plafonds du chat et des taches d'arriere-plan, reglables par variable d'environnement.

Aucune valeur n'est ecrite en dur dans les endroits qui s'en servent : tout vient d'ici
(regle de Bourama : jamais de valeur en dur). Une variable absente, vide, non numerique ou
inferieure ou egale a zero est ignoree et la valeur par defaut s'applique, avec un
avertissement dans les logs pour une valeur invalide.

Decision de Bourama (23/10/2026) : le contenu du chat n'est pas plafonne (message,
historique, resultats d'outils). L'architecture s'en charge deja : le modele archive les
sujets termines, les vieux messages et les vieux resultats d'outils sont remplaces par un
rappel et restent consultables a la demande (core/historique_conversation.py,
core/historique_outils.py). Seuls restent ci-dessous des plafonds de nombre de pieces et
une taille totale de requete, qui protege le serveur (memoire), pas le contenu.
"""
import logging
import os
from datetime import timedelta


def _entier_positif_env(nom: str, defaut: int) -> int:
    brut = os.environ.get(nom)
    if brut is None or not brut.strip():
        return defaut
    try:
        valeur = int(brut.strip())
    except ValueError:
        valeur = 0
    if valeur <= 0:
        logging.warning("Variable %s invalide (%r) : valeur par defaut %s utilisee.", nom, brut, defaut)
        return defaut
    return valeur


# Nombre de pieces par message du chat (api/chat.py).
PLAFOND_OUTILS_PAR_MESSAGE = _entier_positif_env("CLASSINUS_CHAT_MAX_OUTILS_PAR_MESSAGE", 50)
PLAFOND_IMAGES_JOINTES = _entier_positif_env("CLASSINUS_CHAT_MAX_IMAGES_JOINTES", 30)
PLAFOND_ZIPS_JOINTS = _entier_positif_env("CLASSINUS_CHAT_MAX_ZIPS_JOINTS", 20)

# Taille totale d'une requete vers /api/chat, en Mo. Protege la memoire du serveur : la requete
# entiere est lue avant toute validation, et le chat est ouvert aux visiteurs non connectes.
TAILLE_MAX_REQUETE_CHAT_MO = _entier_positif_env("CLASSINUS_CHAT_TAILLE_MAX_REQUETE_MO", 100)

# Age au-dela duquel une tache d'arriere-plan "en cours" est consideree abandonnee et remise
# en attente (core/taches_file_attente.py).
AGE_TACHE_PERIMEE = timedelta(hours=_entier_positif_env("CLASSINUS_TACHE_PERIMEE_HEURES", 2))

# Tours de chat detaches de la connexion (core/tours_detaches.py). Un tour termine reste
# consultable ce temps-la : c'est la fenetre pendant laquelle un rechargement ou une coupure
# de reseau peut encore rattraper la fin du flux. Le plafond de tours termines gardes borne la
# memoire du serveur. Le signe de vie garde la connexion ouverte pendant les longues attentes
# d'outils (les proxys coupent une connexion restee muette trop longtemps).
CONSERVATION_TOUR_DETACHE = timedelta(minutes=_entier_positif_env("CLASSINUS_TOUR_CONSERVATION_MINUTES", 30))
MAX_TOURS_DETACHES_CONSERVES = _entier_positif_env("CLASSINUS_TOURS_CONSERVES_MAX", 200)
DELAI_SIGNE_VIE_FLUX = _entier_positif_env("CLASSINUS_FLUX_SIGNE_VIE_SECONDES", 15)
