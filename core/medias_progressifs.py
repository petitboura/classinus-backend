"""
Affichage progressif des images et des vidéos (22/11/2026, demande de Bourama).

Pourquoi : sur la page bambara, l'utilisateur ne sait pas lire, il comprend ce qu'il voit. Avant,
rechercher_image attendait la source la plus lente, renvoyait une liste au modèle principal, et
l'utilisateur ne voyait rien avant que ce modèle ait fini de réfléchir puis d'écrire ses images.

Maintenant, pour la page bambara seulement :
  1. chaque source d'images (ou chaque source de vidéos, dans l'ordre d'économie de
     core/recherche_video.py) répond de son côté, sans attendre les autres ;
  2. dès qu'une source répond, ses résultats (sans les doublons déjà vus) vont à un petit LLM
     rapide qui choisit ceux qui correspondent vraiment à la demande, en les désignant par numéro ;
  3. les résultats gardés partent tout de suite vers l'écran dans un événement "bloc_media", pendant
     que les autres sources travaillent encore ;
  4. à la fin, le modèle principal reçoit un court résumé (combien ont été affichées, lesquelles),
     et la liste des résultats que le petit LLM n'a pas pu trier, pour qu'il les choisisse comme avant.

Le LLM choisit ce qui s'affiche. Il désigne les résultats par numéro et le code écrit les adresses :
un LLM qui recopie une longue adresse se trompe parfois d'un caractère, une image cassée ne se voit
pas sur une page sans texte.

Le canal (CanalMedias) est la file par laquelle les fils de recherche déposent leurs blocs. La boucle
de core/execution_outils.py la vide pendant qu'elle attend les outils et envoie chaque bloc au chat.
Cette voie existe parce que les outils s'exécutent par un client MCP réseau : un fil d'outil ne peut
pas écrire directement dans le flux de la réponse.

Branchement : core/outils_page_bambara.py marque les deux outils dans la table de routage de la page
(clé "medias_progressifs"). Pour tout autre client, rien ne change.

Les arguments `page` et `nombre` de l'outil gardent leur sens : `page` est transmise aux sources,
`nombre` plafonne ce qui est affiché (jamais au dessus du réglage). Ce chemin n'utilise pas le cache de
core/recherche_image.py : chaque appel interroge toutes les sources disponibles.

Réglages, tous facultatifs (variables d'environnement du backend) :
  MEDIAS_PROGRESSIFS_MODELE                 modèle Groq du tri (défaut : openai/gpt-oss-20b)
  MEDIAS_PROGRESSIFS_DELAI_LLM_SECONDES     délai d'un tri (défaut 8)
  MEDIAS_PROGRESSIFS_LLM_PARALLELES         tris simultanés au plus (défaut 6)
  MEDIAS_PROGRESSIFS_PAR_SOURCE             images demandées à chaque source (défaut 12)
  MEDIAS_PROGRESSIFS_MAX_IMAGES             images affichées au plus (défaut 60)
  MEDIAS_PROGRESSIFS_MAX_VIDEOS             vidéos affichées au plus (défaut 30)
  MEDIAS_PROGRESSIFS_DELAI_SECONDES         durée maximale de toute la recherche (défaut 25)
"""

import concurrent.futures
import json
import logging
import queue
import re
import threading
import time

from groq import Groq

from constantes_agent import get_secret
from core import recherche_image, recherche_video

# Outils concernés, avec le genre de média que chacun renvoie.
OUTILS_PROGRESSIFS = {"rechercher_image": "images", "rechercher_video": "videos"}

# Clé posée sur la route d'un outil (table de routage) pour demander l'affichage progressif.
CLE_ROUTE_PROGRESSIVE = "medias_progressifs"

_MODELE_PAR_DEFAUT = "openai/gpt-oss-20b"
_LONGUEUR_TITRE = 140
_MAX_A_CHOISIR_PAR_LE_MODELE = 30
_MAX_TITRES_RESUME = 20


def _entier(nom, defaut, minimum=1):
    """Entier lu dans l'environnement, jamais plus petit que `minimum`."""
    try:
        return max(minimum, int(get_secret(nom) or defaut))
    except (TypeError, ValueError):
        return defaut


def _entier_argument(arguments, nom, defaut, minimum, maximum):
    """Entier d'un argument de l'outil, borné ; le défaut si l'argument est absent ou invalide."""
    valeur = (arguments or {}).get(nom)
    if valeur is None or isinstance(valeur, bool):
        return defaut
    try:
        return max(minimum, min(int(valeur), maximum))
    except (TypeError, ValueError):
        return defaut


class CanalMedias:
    """File par laquelle les fils de recherche déposent leurs blocs, vidée par la boucle du chat."""

    def __init__(self):
        self._file = queue.Queue()

    def emettre(self, evenement):
        self._file.put(evenement)

    def vider(self):
        """Tout ce qui est arrivé depuis le dernier appel, sans jamais attendre."""
        sortis = []
        while True:
            try:
                sortis.append(self._file.get_nowait())
            except queue.Empty:
                return sortis


# Tris simultanés : protège les quotas du fournisseur quand beaucoup de sources répondent ensemble.
_semaphore_llm = threading.BoundedSemaphore(_entier("MEDIAS_PROGRESSIFS_LLM_PARALLELES", 6))


def _texte_court(valeur, longueur=_LONGUEUR_TITRE):
    texte = " ".join(str(valeur or "").split())
    return texte if len(texte) <= longueur else texte[: longueur - 1].rstrip() + "…"


def _ligne_pour_le_tri(numero, element, genre):
    titre = _texte_court(element.get("titre")) or "(sans titre)"
    if genre == "images":
        origine = element.get("source_domain") or element.get("credit")
    else:
        origine = " ".join(
            str(element.get(cle)) for cle in ("chaine", "duree") if element.get(cle)
        )
    suite = f" ({_texte_court(origine, 60)})" if origine else ""
    return f"{numero}. {titre}{suite}"


def _lire_numeros(texte, nombre):
    """
    Numéros gardés par le tri, lus dans sa réponse. Liste vide si rien ne convient (réponse
    valide), None si la réponse est illisible.
    """
    if not isinstance(texte, str):
        return None
    trouve = re.search(r"\{.*\}", texte, re.DOTALL)
    if not trouve:
        return None
    try:
        donnees = json.loads(trouve.group(0))
    except ValueError:
        return None
    brut = donnees.get("gardes") if isinstance(donnees, dict) else None
    if not isinstance(brut, list):
        return None
    numeros = []
    for valeur in brut:
        try:
            numero = int(valeur)
        except (TypeError, ValueError):
            continue
        if 1 <= numero <= nombre and numero not in numeros:
            numeros.append(numero)
    return numeros


def _demander_numeros(requete, lot, genre):
    """Un appel au petit LLM : les numéros gardés, ou None s'il n'a pas répondu de façon lisible."""
    nom_genre = "images" if genre == "images" else "vidéos"
    consigne = (
        f"Tu tries les résultats d'une recherche de {nom_genre} pour quelqu'un qui ne sait pas lire : "
        "il ne verra que ce que tu gardes. Garde seulement les résultats dont le titre correspond "
        "vraiment à la demande. Écarte ceux sans rapport, les doublons évidents et les publicités. "
        "Si aucun ne convient, garde-en zéro. Réponds uniquement par un JSON de la forme "
        '{"gardes": [numéros]}.'
    )
    lignes = "\n".join(_ligne_pour_le_tri(i, element, genre) for i, element in enumerate(lot, start=1))
    modele = (get_secret("MEDIAS_PROGRESSIFS_MODELE") or _MODELE_PAR_DEFAUT).strip()
    arguments = {
        "model": modele,
        "messages": [
            {"role": "system", "content": consigne},
            {"role": "user", "content": f"Demande : {requete}\n\nRésultats :\n{lignes}"},
        ],
        "temperature": 0,
    }
    if "gpt-oss" in modele:
        arguments["reasoning_effort"] = "low"
    delai = float(_entier("MEDIAS_PROGRESSIFS_DELAI_LLM_SECONDES", 8))
    with _semaphore_llm:
        client = Groq(api_key=get_secret("GROQ_API_KEY"), max_retries=0, timeout=delai)
        completion = client.chat.completions.create(**arguments)
    return _lire_numeros(completion.choices[0].message.content, len(lot))


def _choisir(requete, lot, genre):
    """Les éléments gardés du lot, ou None si le tri a échoué (le lot est alors laissé au modèle principal)."""
    try:
        numeros = _demander_numeros(requete, lot, genre)
    except Exception as e:
        logging.warning("Médias progressifs : tri impossible (%s : %s).", type(e).__name__, e)
        return None
    if numeros is None:
        logging.warning("Médias progressifs : réponse du tri illisible, lot laissé au modèle principal.")
        return None
    return [lot[numero - 1] for numero in numeros]


class _Suivi:
    """État d'un appel de recherche : ce qui est déjà vu, affiché, ou laissé au modèle principal."""

    def __init__(self, genre, requete, canal, id_appel, page=1, nombre=None):
        self.genre = genre
        self.requete = requete
        self.canal = canal
        self.id_appel = id_appel
        self.page = page
        self.verrou = threading.Lock()
        self.vus = set()
        self.affiches = []
        self.non_tries = []
        self.clos = False
        nom_maximum = "MEDIAS_PROGRESSIFS_MAX_IMAGES" if genre == "images" else "MEDIAS_PROGRESSIFS_MAX_VIDEOS"
        self.maximum = _entier(nom_maximum, 60 if genre == "images" else 30)
        # `nombre` demandé par le modèle : il peut seulement réduire le plafond du réglage, jamais le dépasser.
        if nombre is not None:
            self.maximum = min(self.maximum, nombre)

    def _cle(self, element):
        adresse = element.get("url")
        if not isinstance(adresse, str) or not adresse:
            return ""
        return recherche_image.cle_deduplication(adresse) if self.genre == "images" else adresse

    def clore(self):
        """Plus rien n'est émis ni compté après la fin de l'appel (fils encore en route)."""
        with self.verrou:
            self.clos = True

    def traiter_lot(self, nom_source, lot):
        """Retire les doublons, fait trier le lot, puis envoie les gardés à l'écran."""
        with self.verrou:
            if self.clos or len(self.affiches) >= self.maximum:
                return
            nouveaux = []
            for element in lot or []:
                cle = self._cle(element)
                if not cle or cle in self.vus:
                    continue
                self.vus.add(cle)
                nouveaux.append(dict(element))
        if not nouveaux:
            return
        gardes = _choisir(self.requete, nouveaux, self.genre)
        with self.verrou:
            if self.clos:
                return
            if gardes is None:
                self.non_tries.extend(nouveaux)
                return
            gardes = gardes[: max(0, self.maximum - len(self.affiches))]
            if not gardes:
                return
            self.affiches.extend(gardes)
            self.canal.emettre({
                "type": "bloc_media",
                "id_appel": self.id_appel,
                "genre": self.genre,
                "source": nom_source,
                self.genre: gardes,
            })


def _attendre(futures, arret, echeance):
    """Attend les fils jusqu'à l'échéance, en regardant le bouton Arrêter. Ne tue aucun fil."""
    en_attente = set(futures)
    while en_attente and time.monotonic() < echeance:
        if arret is not None and arret.est_demande():
            return
        _, en_attente = concurrent.futures.wait(
            en_attente, timeout=0.1, return_when=concurrent.futures.FIRST_COMPLETED
        )


def _tache_source_image(suivi, nom, fonction, cle, par_source):
    try:
        lot = fonction(suivi.requete, par_source, cle, suivi.page)
    except Exception as e:
        logging.warning("Médias progressifs : source %s indisponible pour %r (%s).", nom, suivi.requete, e)
        return
    suivi.traiter_lot(nom, lot)


def _chercher_images(suivi, arret, echeance):
    sources = recherche_image.sources_disponibles()
    if not sources:
        logging.warning("Médias progressifs : aucune source d'images disponible.")
        return
    par_source = _entier("MEDIAS_PROGRESSIFS_PAR_SOURCE", 12)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(sources)))
    try:
        taches = [
            pool.submit(_tache_source_image, suivi, nom, fonction, cle, par_source)
            for nom, fonction, cle in sources
        ]
        _attendre(taches, arret, echeance)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _chercher_videos(suivi, arret, echeance):
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=_entier("MEDIAS_PROGRESSIFS_LLM_PARALLELES", 6) + 1)
    tris = []
    try:
        # La recherche passe par les sources dans l'ordre d'économie de recherche_video.py. Chaque
        # lot part au tri sans bloquer la source suivante.
        def sur_lot(nom_source, lot):
            tris.append(pool.submit(suivi.traiter_lot, nom_source, lot))

        recherche = pool.submit(
            recherche_video.rechercher_videos, suivi.requete, min(suivi.maximum, 50), suivi.page, sur_lot
        )
        _attendre([recherche], arret, echeance)
        if recherche.done() and recherche.exception() is not None:
            logging.warning("Médias progressifs : recherche de vidéos en erreur (%s).", recherche.exception())
        _attendre(list(tris), arret, echeance)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _resume_element(element, genre):
    resume = {"titre": _texte_court(element.get("titre"), 100), "url": element.get("url")}
    if genre == "images":
        if element.get("credit"):
            resume["credit"] = _texte_court(element.get("credit"), 60)
    else:
        for cle in ("chaine", "duree"):
            if element.get(cle):
                resume[cle] = element.get(cle)
    return resume


def _resultat_pour_le_modele(suivi):
    """Ce que le modèle principal reçoit : un résumé court, jamais la liste complète des résultats."""
    singulier, pluriel = ("image", "images") if suivi.genre == "images" else ("vidéo", "vidéos")
    nombre = len(suivi.affiches)
    corps = {"affichees": nombre, "page": suivi.page, "page_suivante_suggeree": suivi.page + 1}
    notes = []
    if nombre:
        corps["titres_affiches"] = [
            _texte_court(element.get("titre"), 80) for element in suivi.affiches[:_MAX_TITRES_RESUME]
        ]
        notes.append(
            f"{nombre} {pluriel if nombre > 1 else singulier} ont déjà été affichées à l'utilisateur, "
            "triées, au fur et à mesure de la recherche. Ne recopie aucune de ces adresses dans ta réponse : "
            "elles sont déjà à l'écran. Pas besoin de relancer la même recherche."
        )
    else:
        notes.append(f"Aucune {singulier} n'a été retenue pour la demande, rien n'est affiché.")
    if suivi.non_tries:
        cle_liste = "images_trouvees" if suivi.genre == "images" else "videos_trouvees"
        corps[cle_liste] = [
            _resume_element(element, suivi.genre) for element in suivi.non_tries[:_MAX_A_CHOISIR_PAR_LE_MODELE]
        ]
        notes.append(
            f"Les résultats de {cle_liste} n'ont pas pu être triés automatiquement et ne sont PAS affichés : "
            "garde seulement ceux qui correspondent vraiment à la demande, et montre-les comme d'habitude."
        )
    corps["note"] = " ".join(notes)
    return json.dumps(corps, ensure_ascii=False)


def executer(nom_outil, arguments, canal, id_appel, arret=None):
    """
    Exécute rechercher_image ou rechercher_video avec affichage progressif. Renvoie le texte du
    résultat de l'outil pour le modèle principal. Ne lève jamais : un problème devient un résultat.
    """
    genre = OUTILS_PROGRESSIFS.get(nom_outil)
    if genre is None:
        return f"Erreur : l'outil {nom_outil} n'a pas d'affichage progressif."
    requete = str((arguments or {}).get("requete") or "").strip()
    if not requete:
        return "Erreur : indique ce qu'il faut chercher."
    # `page` et `nombre` gardent le sens qu'ils ont dans rechercher_image et rechercher_video : la page des
    # sources (pour « en voir plus » avec page=2) et le nombre voulu. Une valeur invalide revient au défaut,
    # comme le fait la recherche complète (rechercher_images).
    maximum_outil = 100 if genre == "images" else 50
    page = _entier_argument(arguments, "page", 1, 1, 1000)
    nombre = _entier_argument(arguments, "nombre", None, 1, maximum_outil)
    suivi = _Suivi(genre, requete, canal, id_appel, page=page, nombre=nombre)
    echeance = time.monotonic() + _entier("MEDIAS_PROGRESSIFS_DELAI_SECONDES", 25)
    try:
        if genre == "images":
            _chercher_images(suivi, arret, echeance)
        else:
            _chercher_videos(suivi, arret, echeance)
    except Exception as e:
        logging.error("Médias progressifs : %s a échoué pour %r (%s).", nom_outil, requete, e)
    finally:
        suivi.clore()
    with suivi.verrou:
        if not suivi.affiches and not suivi.non_tries and not suivi.vus:
            # Rien n'est arrivé : même message que la recherche complète, pour que le modèle réagisse pareil.
            return f"Aucune {'image' if genre == 'images' else 'vidéo'} trouvée pour cette recherche."
        return _resultat_pour_le_modele(suivi)
