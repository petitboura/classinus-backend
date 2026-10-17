"""Consignes propres au client Thonny (plugin thonny-classinus), lot 1 du 14/10/2026, demande Bourama.

Le site et Thonny n'affichent pas les mêmes choses. Les consignes d'affichage du site (schémas,
fiches, QCM, animations, cartes de liens, guide...) ne servent à rien dans le panneau Thonny,
coûtent des jetons à chaque message et contredisent les consignes de Thonny. Quand le client
se déclare Thonny (champ `client` de la requête de chat), le prompt système reçoit donc :
  1. les blocs de plateforme utiles hors affichage (paragraphes, liens, recherche de documents,
     outils de génération, faits vérifiables, appels d'outils, arbitrage de calcul, contexte
     invisible, mémoire de l'élève), repris tels quels depuis profils_agents.py pour ne jamais
     dériver du site ;
  2. les consignes de Thonny (core/consignes_thonny.txt), avec le nom des boutons du panneau
     dans la langue de l'élève, envoyé par le plugin (`libelles_client`).
Ni l'identité de l'agent, ni les outils, ni les consignes pédagogiques ne sont touchés ici.
"""

import functools
import logging
import os
import re

from profils_agents import (
    INSTRUCTIONS_FORMATS_AFFICHAGE,
    INSTRUCTIONS_ARBITRAGE_CALCUL,
    REGLE_CONTEXTE_INVISIBLE,
    REGLE_MEMOIRE_ELEVE,
)

CLIENT_THONNY = "thonny"

# Boutons du panneau Thonny cités par les consignes. Le plugin envoie leur nom dans la langue de l'élève.
LIBELLES_AUTORISES = (
    "envoyer_code",
    "corriger_code",
    "expliquer_erreur",
    "expliquer_selection",
    "nouvelle_conversation",
    "copier",
    "inserer",
    "nouvel_onglet",
)
LONGUEUR_MAX_LIBELLE = 60

# Sections de INSTRUCTIONS_FORMATS_AFFICHAGE qui n'ont rien à voir avec l'affichage du site.
_BALISES_REPRISES = (
    "paragraphes",
    "recherche_documents",
    "outils_generation_action",
    "faits_verifiables",
    "appels_outils",
)
# Début du passage de <liens> qui explique comment lire le contenu d'un lien (outils de lecture).
_DEBUT_LECTURE_LIENS = "Quand un lien fait partie de ce qu'on te donne à lire"
# Phrase de <recherche_documents> qui décrit la carte de fichier du site.
_PHRASE_CARTE_FICHIER_SITE = " : l'interface propose alors l'aperçu, le téléchargement et l'ajout à la bibliothèque"

_REGLE_LIENS = """<liens>
Écris une URL seulement si elle vient réellement d'un outil ou de l'utilisateur, jamais générée ou supposée, même plausible. Si on t'en demande une et qu'aucun outil n'est disponible, dis-le clairement. Écris chaque lien sous la forme [texte](url) où le texte est le vrai nom de la ressource (nom du fichier, titre de l'article), jamais l'URL brute ni un texte générique comme « ici » ou « ce lien ».

{lecture}
</liens>"""

_MODELE_CONSIGNES = os.path.join(os.path.dirname(__file__), "consignes_thonny.txt")


def est_client_thonny(client):
    return isinstance(client, str) and client.strip().lower() == CLIENT_THONNY


def _section(balise):
    """Une section balisée de INSTRUCTIONS_FORMATS_AFFICHAGE.

    Les balises d'une section sont seules sur leur ligne : une simple mention dans une phrase
    (ex. « voir <liens> ») ne compte pas comme un début de section.
    """
    ouverture = re.search(r"^<%s>[ \t]*$" % re.escape(balise), INSTRUCTIONS_FORMATS_AFFICHAGE, re.MULTILINE)
    fermeture = re.search(r"^</%s>[ \t]*$" % re.escape(balise), INSTRUCTIONS_FORMATS_AFFICHAGE, re.MULTILINE)
    if not ouverture or not fermeture or fermeture.start() < ouverture.start():
        logging.warning("prompt Thonny : section %s introuvable dans les consignes de plateforme", balise)
        return ""
    return INSTRUCTIONS_FORMATS_AFFICHAGE[ouverture.start() : fermeture.end()].rstrip()


def _lecture_des_liens():
    section = _section("liens")
    debut = section.find(_DEBUT_LECTURE_LIENS)
    fin = section.rfind("</liens>")
    if debut < 0 or fin < 0:
        return ""
    return section[debut:fin].strip()


def _regle_liens():
    return _REGLE_LIENS.replace("{lecture}", _lecture_des_liens()).replace("\n\n\n", "\n\n")


def blocs_plateforme(avec_memoire):
    """Remplace INSTRUCTIONS_FORMATS_AFFICHAGE, arbitrage, contexte invisible, état de l'appli et mémoire."""
    sections = []
    for balise in _BALISES_REPRISES:
        texte = _section(balise)
        if balise == "recherche_documents":
            texte = texte.replace(_PHRASE_CARTE_FICHIER_SITE, "")
        if texte:
            sections.append(texte)
    parties = ["\n\n" + sections[0]] if sections else [""]
    parties.append(_regle_liens())
    parties.extend(sections[1:])
    bloc = "\n\n".join(p for p in parties if p)
    return bloc + INSTRUCTIONS_ARBITRAGE_CALCUL + REGLE_CONTEXTE_INVISIBLE + (REGLE_MEMOIRE_ELEVE if avec_memoire else "")


@functools.lru_cache(maxsize=1)
def _lire_modele():
    try:
        with open(_MODELE_CONSIGNES, encoding="utf-8") as f:
            return f.read().strip()
    except OSError as e:
        logging.error("prompt Thonny : consignes_thonny.txt illisible : %s", e)
        return ""


def _libelle_propre(valeur):
    texte = re.sub(r"[\s{}`]+", " ", valeur).strip()
    return texte[:LONGUEUR_MAX_LIBELLE]


def libelles_valides(libelles):
    """Garde seulement les noms de boutons connus, en texte court et sans accolades."""
    if not isinstance(libelles, dict):
        return {}
    propres = {}
    for cle in LIBELLES_AUTORISES:
        valeur = libelles.get(cle)
        if isinstance(valeur, str) and valeur.strip():
            propre = _libelle_propre(valeur)
            if propre:
                propres[cle] = propre
    return propres


def _libelle_par_defaut(cle):
    return cle.replace("_", " ").capitalize()


def consignes(libelles=None):
    """Les consignes de Thonny, avec le nom des boutons dans la langue de l'élève."""
    modele = _lire_modele()
    if not modele:
        return ""
    propres = libelles_valides(libelles)
    texte = re.sub(r"\{(\w+)\}", lambda m: propres.get(m.group(1)) or _libelle_par_defaut(m.group(1)), modele)
    return "\n\n" + texte
