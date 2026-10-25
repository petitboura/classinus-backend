"""
Sites visés par un appel d'outil, pour l'affichage du chat (21/10/2026, demande
Bourama : le chat montre le logo du site ou de la source concernée par l'outil,
jamais celui de l'outil lui-même, comme Tavily).

Une ligne d'outil reçoit une liste de noms de domaine ("youtube.com",
"arxiv.org"...) ; le frontend choisit le logo (vrai fichier de logo si on l'a,
sinon l'icône publiée par le site). Aucun appel réseau ici, uniquement la lecture
des arguments de l'appel.

Outils concernés :
- recherche et lecture de vidéo : YouTube ;
- recherche de document : la source nommée, ou toutes les sources interrogées
  quand l'étudiant n'en a nommé aucune (le chat montre alors une rangée de logos) ;
- lecture d'un document Internet Archive : archive.org ;
- lecture d'un fichier externe : le site du lien ;
- Tavily, seulement les outils qui agissent sur un site précis (extraire,
  explorer, cartographier). La recherche web et la recherche approfondie ne
  visent aucun site : elles gardent leur icône.

Tout échec (arguments invalides, source inconnue) donne une liste vide, jamais
une exception : l'affichage ne doit jamais faire échouer un outil.
"""

import logging
import re
from urllib.parse import urlparse

DOMAINES_FIXES = {
    "rechercher_video": ["youtube.com"],
    "lire_video": ["youtube.com"],
    "lire_document_internet_archive": ["archive.org"],
}

# Outils Tavily qui agissent sur un site précis, et le nom de leur paramètre
# d'adresse (une adresse ou une liste d'adresses).
PARAMETRES_ADRESSE_TAVILY = {
    "tavily_extract": ("urls", "url"),
    "tavily_crawl": ("url", "urls"),
    "tavily_map": ("url", "urls"),
}

# Nombre maximal de domaines envoyés pour une même ligne.
MAX_DOMAINES = 8


def domaine_de_adresse(adresse):
    """Nom de domaine d'une adresse web, sans "www.", en minuscules, ou None."""
    if not isinstance(adresse, str):
        return None
    texte = adresse.strip()
    if not texte:
        return None
    if "://" not in texte:
        texte = "https://" + texte
    try:
        hote = urlparse(texte).hostname
    except ValueError:
        return None
    if not hote or "." not in hote:
        return None
    hote = hote.lower()
    return hote[4:] if hote.startswith("www.") else hote


def _domaines_de_adresses(valeur):
    adresses = valeur if isinstance(valeur, list) else [valeur]
    domaines = []
    for adresse in adresses:
        domaine = domaine_de_adresse(adresse)
        if domaine and domaine not in domaines:
            domaines.append(domaine)
    return domaines


def _domaines_recherche_document(arguments):
    from core.sources_documents_externes import (
        SOURCES,
        SourceInconnue,
        identifiant_source,
        recherche_melangee_active,
    )

    source = arguments.get("source")
    if not str(source or "").strip() and recherche_melangee_active():
        cles = list(SOURCES)
    else:
        try:
            cles = [identifiant_source(source)]
        except SourceInconnue:
            return []
    return [SOURCES[cle]["domaine"] for cle in cles if SOURCES[cle].get("domaine")]


_MOTIF_NOM_DE_DOMAINE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)


def _domaine_nom_seul(valeur):
    """Le domaine tel quel s'il ressemble vraiment à un nom de domaine, sinon None (texte libre refusé)."""
    texte = str(valeur or "").strip().lower().rstrip(".")
    return texte if _MOTIF_NOM_DE_DOMAINE.fullmatch(texte) else None


def domaines_de_l_appel(nom_outil, arguments):
    """Liste des domaines visés par cet appel d'outil ([] si aucun site précis)."""
    try:
        arguments = arguments if isinstance(arguments, dict) else {}
        if nom_outil in DOMAINES_FIXES:
            return list(DOMAINES_FIXES[nom_outil])
        if nom_outil == "rechercher_document_externe":
            return _domaines_recherche_document(arguments)[:MAX_DOMAINES]
        if nom_outil == "gerer_execution_code" and arguments.get("action") == "demander_acces_reseau":
            domaine = _domaine_nom_seul(arguments.get("domain"))
            return [domaine] if domaine else []
        if nom_outil == "lire_document_externe":
            return _domaines_de_adresses(arguments.get("url"))[:MAX_DOMAINES]
        if nom_outil in PARAMETRES_ADRESSE_TAVILY:
            for parametre in PARAMETRES_ADRESSE_TAVILY[nom_outil]:
                domaines = _domaines_de_adresses(arguments.get(parametre))
                if domaines:
                    return domaines[:MAX_DOMAINES]
        return []
    except Exception as e:
        logging.error(f"AFFICHAGE : domaines de l'outil {nom_outil} illisibles ({e}).")
        return []


# Langages de l'outil Exécution de code dont le chat montre le logo (24/10/2026,
# demande Bourama : le logo du langage se pose en petit badge sur l'icône Play de
# la ligne). Mêmes valeurs que le paramètre `language` de gerer_execution_code
# (core/outils_execution_code.py), Python étant le langage par défaut de l'outil.
LANGAGES_EXECUTION_CODE = ("python", "javascript", "typescript", "bash")
LANGAGE_EXECUTION_CODE_DEFAUT = "python"


def langage_de_l_appel(nom_outil, arguments):
    """
    Langage lancé par cet appel, seulement pour l'action run_code de l'outil
    Exécution de code ("python", "javascript", "typescript" ou "bash"). None pour
    tout autre outil ou toute autre action (commande shell, fichiers...) : ces
    lignes gardent leur icône seule. Un langage absent donne le langage par
    défaut de l'outil, un langage inconnu donne None (jamais une icône devinée).
    """
    try:
        if nom_outil != "gerer_execution_code" or not isinstance(arguments, dict):
            return None
        if arguments.get("action") != "run_code":
            return None
        langage = arguments.get("language") or LANGAGE_EXECUTION_CODE_DEFAUT
        return langage if langage in LANGAGES_EXECUTION_CODE else None
    except Exception as e:
        logging.error(f"AFFICHAGE : langage de l'outil {nom_outil} illisible ({e}).")
        return None
