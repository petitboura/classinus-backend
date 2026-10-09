"""
Lecture du texte d'un document Internet Archive (livre, PDF) pour Classinus.

Lot 2 du chantier Internet Archive (09/10/2026, demande Bourama). Le lot 1
trouve le document et donne son lien ; ce module lit son contenu pour
répondre à des questions ou citer des passages. Sert l'outil
lire_document_internet_archive (core/outils_lecture_document_archive.py).

Trois niveaux, essayés dans cet ordre :

1. Le texte déjà extrait par Internet Archive (fichier "DjVuTXT", puis tout
   autre fichier texte du document). Rapide et sans calcul de notre côté.
2. À défaut, le PDF du document, seulement s'il est assez petit, lu avec
   l'extraction PDF existante (core/extraction_documents.py).
3. À défaut, une explication claire : le modèle donne le lien de la page et
   dit qu'il ne peut pas lire le contenu, sans rien inventer.

Un livre sous prêt numérique (accès réservé) ne se télécharge pas sans
compte : il est reconnu et traité comme le niveau 3, avec le lien de la page.

Le texte est lu par tranches. La réponse indique à quel caractère reprendre
pour lire la suite. Le paramètre `rechercher` permet de trouver les passages
qui contiennent un mot ou une expression dans un livre long, sans le lire
en entier.

Le retour est toujours un texte destiné au modèle, jamais une exception.

Le relais des PDF vers le visionneur est le lot 3 : rien ici n'y touche.

Réglages par variables d'environnement :
- LECTURE_ARCHIVE_LONGUEUR_MAX : caractères lus par tranche (20000 par défaut)
- LECTURE_ARCHIVE_TEXTE_TAILLE_MAX : taille maximale du fichier texte
  téléchargé, en octets (40 Mo par défaut)
- LECTURE_ARCHIVE_PDF_TAILLE_MAX : taille maximale d'un PDF lu en secours,
  en octets (25 Mo par défaut)
- LECTURE_ARCHIVE_DELAI : délai maximal d'une requête, en secondes (30)
- LECTURE_ARCHIVE_MEMOIRE_SECONDES : durée de mémorisation d'un document lu
  (1800 par défaut)
- LECTURE_ARCHIVE_MEMOIRE_TAILLE : nombre de documents gardés (6 par défaut)

NON TESTÉ EN CONDITIONS RÉELLES au moment de l'écriture (09/10/2026) : le
serveur de développement n'a pas accès à archive.org. À vérifier en
production au premier vrai essai.
"""

import logging
import os
import re
import threading
import time
from urllib.parse import quote

import requests

_URL_METADONNEES = "https://archive.org/metadata/{id}"
_URL_FICHIER = "https://archive.org/download/{id}/{fichier}"
_URL_PAGE = "https://archive.org/details/{id}"

_REGEX_ID_DANS_LIEN = re.compile(
    r"archive\.org/(?:details|download|stream|embed)/([A-Za-z0-9][A-Za-z0-9._-]{0,150})"
)
_REGEX_ID_SEUL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,150}$")

_NOMBRE_PASSAGES_MAX = 6
_MARGE_PASSAGE = 300
_TAILLE_BLOC_TELECHARGEMENT = 64 * 1024

_verrou = threading.Lock()
_memoire = {}  # id -> (instant, informations du document)


class _DocumentIllisible(Exception):
    """Le contenu ne peut pas être lu ; le message est destiné au modèle."""


def _entier_env(nom, defaut):
    try:
        return int(os.environ.get(nom, defaut))
    except (TypeError, ValueError):
        return defaut


def extraire_identifiant(texte):
    """Accepte une adresse archive.org ou directement l'identifiant du document."""
    texte = (texte or "").strip()
    correspondance = _REGEX_ID_DANS_LIEN.search(texte)
    if correspondance:
        return correspondance.group(1)
    if _REGEX_ID_SEUL.match(texte):
        return texte
    return None


def _lire_memoire(identifiant):
    duree = _entier_env("LECTURE_ARCHIVE_MEMOIRE_SECONDES", 1800)
    with _verrou:
        entree = _memoire.get(identifiant)
        if entree and time.time() - entree[0] < duree:
            return entree[1]
        _memoire.pop(identifiant, None)
    return None


def _ecrire_memoire(identifiant, infos):
    taille_max = max(1, _entier_env("LECTURE_ARCHIVE_MEMOIRE_TAILLE", 6))
    with _verrou:
        _memoire[identifiant] = (time.time(), infos)
        while len(_memoire) > taille_max:
            plus_ancien = min(_memoire, key=lambda cle: _memoire[cle][0])
            _memoire.pop(plus_ancien, None)


def _delai():
    return _entier_env("LECTURE_ARCHIVE_DELAI", 30)


def _recuperer_metadonnees(identifiant):
    reponse = requests.get(_URL_METADONNEES.format(id=quote(identifiant, safe="")), timeout=_delai())
    reponse.raise_for_status()
    donnees = reponse.json()
    if not isinstance(donnees, dict) or not donnees.get("files"):
        raise _DocumentIllisible(
            "Aucun document trouvé sous cet identifiant sur Internet Archive. "
            "Vérifie le lien ou relance une recherche."
        )
    return donnees


def _est_vrai(valeur):
    return str(valeur).strip().lower() in ("true", "1", "yes")


def _taille_fichier(fichier):
    try:
        return int(fichier.get("size") or 0)
    except (TypeError, ValueError):
        return 0


def _choisir_fichier_texte(fichiers):
    """Le texte extrait par Internet Archive, sinon tout autre fichier texte."""
    for fichier in fichiers:
        nom = fichier.get("name") or ""
        if fichier.get("format") == "DjVuTXT" or nom.endswith("_djvu.txt"):
            return fichier
    for fichier in fichiers:
        nom = (fichier.get("name") or "").lower()
        if nom.endswith(".txt") and not nom.endswith("_meta.txt") and fichier.get("source") != "metadata":
            return fichier
    return None


def _choisir_fichier_pdf(fichiers):
    candidats = [
        f for f in fichiers
        if (f.get("name") or "").lower().endswith(".pdf") and f.get("source") != "metadata"
    ]
    if not candidats:
        return None
    # Les PDF "texte" (avec la couche de texte) avant les autres.
    candidats.sort(key=lambda f: 0 if "text" in str(f.get("format") or "").lower() else 1)
    return candidats[0]


def _telecharger(identifiant, nom_fichier, taille_max):
    """
    Télécharge le fichier en flux, sans jamais dépasser taille_max octets.
    Renvoie les octets ; lève _DocumentIllisible avec un message clair sinon.
    """
    url = _URL_FICHIER.format(id=quote(identifiant, safe=""), fichier=quote(nom_fichier, safe="/"))
    with requests.get(url, timeout=_delai(), stream=True) as reponse:
        if reponse.status_code in (401, 403):
            raise _DocumentIllisible("acces_reserve")
        if reponse.status_code == 404:
            raise _DocumentIllisible("Le fichier n'existe plus sur Internet Archive.")
        reponse.raise_for_status()
        morceaux = []
        total = 0
        for bloc in reponse.iter_content(_TAILLE_BLOC_TELECHARGEMENT):
            total += len(bloc)
            if total > taille_max:
                raise _DocumentIllisible("trop_gros")
            morceaux.append(bloc)
    return b"".join(morceaux)


def _nettoyer_texte(texte):
    texte = texte.replace("\x0c", "\n\n").replace("\r\n", "\n")
    texte = re.sub(r"[ \t]+\n", "\n", texte)
    texte = re.sub(r"\n{4,}", "\n\n\n", texte)
    return texte.strip()


def _charger_document(identifiant):
    """
    Renvoie {"texte", "titre", "origine"} ou lève _DocumentIllisible.
    "origine" vaut "texte" (extrait par Internet Archive) ou "pdf".
    """
    metadonnees = _recuperer_metadonnees(identifiant)
    infos_meta = metadonnees.get("metadata") or {}
    titre = infos_meta.get("title") or identifiant
    if isinstance(titre, list):
        titre = titre[0] if titre else identifiant
    fichiers = metadonnees.get("files") or []

    if _est_vrai(infos_meta.get("access-restricted-item")):
        raise _DocumentIllisible("acces_reserve")

    taille_texte_max = _entier_env("LECTURE_ARCHIVE_TEXTE_TAILLE_MAX", 40 * 1024 * 1024)
    taille_pdf_max = _entier_env("LECTURE_ARCHIVE_PDF_TAILLE_MAX", 25 * 1024 * 1024)

    fichier_pdf = _choisir_fichier_pdf(fichiers)
    # Lot 3 : un PDF ouvrable dans le visionneur (relais du backend) s'il
    # n'est pas plus gros que le plafond du relais.
    plafond_relais = _entier_env("ARCHIVE_RELAIS_TAILLE_MAX", 500 * 1024 * 1024)
    pdf_visionneur = bool(fichier_pdf) and (_taille_fichier(fichier_pdf) or 0) <= plafond_relais
    raison_texte = None
    fichier_texte = _choisir_fichier_texte(fichiers)
    if fichier_texte:
        try:
            octets = _telecharger(identifiant, fichier_texte["name"], taille_texte_max)
            texte = _nettoyer_texte(octets.decode("utf-8", errors="replace"))
            if texte:
                return {"texte": texte, "titre": str(titre), "origine": "texte", "pdf_visionneur": pdf_visionneur}
            logging.info(f"LECTURE ARCHIVE ({identifiant}) : fichier texte vide, essai du PDF")
        except _DocumentIllisible as e:
            if str(e) == "acces_reserve":
                raise
            raison_texte = str(e)
            logging.info(f"LECTURE ARCHIVE ({identifiant}) : texte inutilisable ({e}), essai du PDF")

    if fichier_pdf:
        taille = _taille_fichier(fichier_pdf)
        if taille and taille > taille_pdf_max:
            raise _DocumentIllisible("pdf_trop_gros")
        octets = _telecharger(identifiant, fichier_pdf["name"], taille_pdf_max)
        from core.extraction_documents import extraire_texte_pdf

        texte = _nettoyer_texte(extraire_texte_pdf(octets))
        if texte:
            return {"texte": texte, "titre": str(titre), "origine": "pdf", "pdf_visionneur": pdf_visionneur}

    raise _DocumentIllisible(raison_texte if raison_texte == "trop_gros" else "aucun_texte")


def _explication_illisible(identifiant, raison):
    page = _URL_PAGE.format(id=identifiant)
    if raison == "acces_reserve":
        return (
            f"Ce document est en prêt numérique sur Internet Archive : son contenu n'est pas lisible sans "
            f"compte et je ne peux pas le lire. Donne seulement le lien de sa page à l'étudiant : {page} . "
            f"Ne devine ni ne résume ce qu'il contient."
        )
    if raison == "pdf_trop_gros":
        return (
            f"Internet Archive n'a pas extrait le texte de ce document, et son PDF est trop gros pour que je "
            f"le lise ici. Donne le lien de la page à l'étudiant : {page} . Ne devine ni ne résume ce qu'il contient."
        )
    if raison == "trop_gros":
        return (
            f"Le texte de ce document est trop gros pour être lu ici. Donne le lien de la page à "
            f"l'étudiant : {page} . Ne devine ni ne résume ce qu'il contient."
        )
    if raison == "aucun_texte":
        return (
            f"Je n'ai trouvé aucun texte lisible pour ce document (il s'agit peut-être d'images seules, "
            f"d'une vidéo ou d'un enregistrement audio). Donne le lien de la page à l'étudiant : {page} . "
            f"Ne devine ni ne résume ce qu'il contient."
        )
    return f"{raison} Lien de la page : {page} ."


def _lien_visionneur(identifiant):
    """Lien du PDF dans le visionneur (relais du lot 3), ou None si l'adresse du backend est inconnue."""
    from core.relais_pdf_archive import lien_pdf_visionneur

    return lien_pdf_visionneur(identifiant)


def _tranche(identifiant, infos, a_partir_du_caractere):
    texte = infos["texte"]
    total = len(texte)
    longueur = max(1000, _entier_env("LECTURE_ARCHIVE_LONGUEUR_MAX", 20000))
    debut = max(0, a_partir_du_caractere)
    if debut >= total:
        return f"Le document fait {total} caractères : la position {debut} est après la fin."

    fin = min(total, debut + longueur)
    if fin < total:
        # Coupe sur une fin de ligne ou un espace proche, pour ne pas couper un mot.
        coupure = max(texte.rfind("\n", debut, fin), texte.rfind(" ", debut, fin))
        if coupure > debut + longueur // 2:
            fin = coupure

    origine = "texte extrait par Internet Archive" if infos["origine"] == "texte" else "PDF lu par Classinus"
    entete = (
        f"Contenu du document « {infos['titre']} » ({_URL_PAGE.format(id=identifiant)}), {origine}, "
        f"{total} caractères au total. Cette tranche va du caractère {debut} au caractère {fin}. "
    )
    if fin < total:
        entete += (
            f"Pour lire la suite, rappelle lire_document_internet_archive avec a_partir_du_caractere={fin}. "
        )
    else:
        entete += "Cette tranche va jusqu'à la fin du document. "
    lien_pdf = _lien_visionneur(identifiant) if infos.get("pdf_visionneur") else None
    if lien_pdf:
        entete += (
            f"Si l'étudiant veut ouvrir le PDF, écris son lien en markdown [titre]({lien_pdf}) avec cette "
            f"adresse exacte, sans la modifier : il s'ouvre dans le visionneur du chat. "
        )
    entete += (
        "Le texte vient d'une numérisation : il peut contenir des erreurs de lecture. "
        "Base-toi uniquement sur ce texte, sans rien inventer au delà, et donne le lien de la page."
    )
    return f"{entete}\n\n{texte[debut:fin]}"


def _passages(identifiant, infos, recherche):
    texte = infos["texte"]
    motif = re.compile(re.escape(recherche.strip()), re.IGNORECASE)
    resultats = []
    dernier_fin = -1
    for correspondance in motif.finditer(texte):
        if correspondance.start() < dernier_fin:
            continue
        debut = max(0, correspondance.start() - _MARGE_PASSAGE)
        fin = min(len(texte), correspondance.end() + _MARGE_PASSAGE)
        resultats.append((correspondance.start(), texte[debut:fin].replace("\n", " ")))
        dernier_fin = fin
        if len(resultats) >= _NOMBRE_PASSAGES_MAX:
            break

    page = _URL_PAGE.format(id=identifiant)
    if not resultats:
        return (
            f"Aucun passage de « {infos['titre']} » ({page}) ne contient « {recherche.strip()} ». "
            f"Essaie un autre mot, une autre orthographe, ou lis le document par tranches. Ne devine pas ce qu'il dit."
        )
    lignes = [
        f"Passages de « {infos['titre']} » ({page}) qui contiennent « {recherche.strip()} » "
        f"(les {len(resultats)} premiers). La position indique où lire autour avec a_partir_du_caractere. "
        f"Le texte vient d'une numérisation : il peut contenir des erreurs de lecture."
    ]
    for position, extrait in resultats:
        lignes.append(f"\n[position {position}] … {extrait} …")
    return "\n".join(lignes)


def lire_document_archive(url_ou_id, a_partir_du_caractere=0, rechercher=""):
    """
    Renvoie un texte pour le modèle : une tranche du contenu du document, ou
    les passages qui contiennent `rechercher`, ou à défaut une explication
    claire de l'impossibilité. Ne lève jamais d'exception.
    """
    identifiant = extraire_identifiant(url_ou_id)
    if not identifiant:
        return "Lien non reconnu : donne l'adresse d'un document Internet Archive (archive.org/details/...) ou son identifiant."

    try:
        a_partir_du_caractere = int(a_partir_du_caractere or 0)
    except (TypeError, ValueError):
        a_partir_du_caractere = 0

    infos = _lire_memoire(identifiant)
    if infos is None:
        try:
            infos = _charger_document(identifiant)
            _ecrire_memoire(identifiant, infos)
        except _DocumentIllisible as e:
            return _explication_illisible(identifiant, str(e))
        except requests.Timeout:
            logging.error(f"ERREUR LECTURE ARCHIVE ({identifiant}) : délai dépassé")
            return (
                "Internet Archive n'a pas répondu à temps. Réessaie dans un instant ; si ça échoue encore, "
                f"donne seulement le lien de la page : {_URL_PAGE.format(id=identifiant)} ."
            )
        except Exception as e:
            logging.error(f"ERREUR LECTURE ARCHIVE ({identifiant}) : {type(e).__name__} {str(e)[:200]}")
            return (
                "La lecture de ce document a échoué. Réessaie une fois ; si ça échoue encore, "
                f"donne seulement le lien de la page à l'étudiant : {_URL_PAGE.format(id=identifiant)} . "
                "Ne devine pas ce que contient le document."
            )

    if rechercher and rechercher.strip():
        return _passages(identifiant, infos, rechercher)
    return _tranche(identifiant, infos, a_partir_du_caractere)
