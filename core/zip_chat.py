"""
Dézipage d'une archive jointe à un message de chat (26/09/2026, chantier
"zip en conversation", plan validé par Bourama).

Différent de core/import_zip.py (bibliothèque) : ici, RIEN n'est stocké
en base ni dans la bibliothèque -- un zip joint au chat reste un
artefact éphémère de la conversation, exactement comme un document seul
(voir api/uploads.py:uploader_document_chat). Le contenu de chaque
fichier de l'archive n'est PAS injecté automatiquement dans le message
(demande explicite Bourama : "le LLM décide lui-même lequel lire") --
seul un sommaire (nom + statut lisible/non lisible) est injecté, et
core/outils_fichiers_conversation.py:gerer_fichier_conversation expose
une action "lire" pour aller chercher le texte d'un fichier précis à la
demande.

Cycle de vie d'un job (volontairement en mémoire, pas en base : un job
ne vit que le temps d'un aller-retour de chat, perdu si le serveur
redémarre -- cohérent avec le caractère éphémère de ces fichiers) :
1. demarrer_extraction_zip_chat() est appelé DÈS l'upload (avant même
   que l'étudiant clique Envoyer) -- crée le job et lance le dépliage
   dans un thread à part, renvoie immédiatement un job_id.
2. Si le job est déjà termine=True au moment de l'envoi du message,
   core/main.py:chat() n'a rien à streamer -- il construit directement
   le sommaire.
3. Sinon, iterer_statuts() reprend le travail là où le thread de fond en
   est, en streamant un événement statut/statut_termine PAR FICHIER déjà
   connu (nom_outil/nom_lisible identiques à la suite -> fusion "×N"
   automatique côté frontend, voir OutilResultatBulle.tsx:cleFusion),
   jusqu'à ce que le job soit terminé.

Nommage des lignes de statut (demande Bourama, 26/09/2026) :
- Fichiers directement dans l'archive : "Dézipage de {nom_zip}" (tous le
  même libellé -> fusionnés en une ligne "×N").
- Fichiers d'un zip imbriqué : "Dézipage de {zip_imbrique}, dans
  {zip_parent}" (une ligne PROPRE à ce niveau, son propre "×N" -- jamais
  mélangée avec les fichiers du zip parent).
- Deux zips différents joints au même message : deux nom_zip différents
  -> deux lignes indépendantes, jamais fusionnées entre elles.
"""

import logging
import threading
import time
import uuid

from extraction_documents import (
    TYPES_DOCUMENTS_AUTORISES,
    LONGUEUR_MAX_TEXTE_EXTRAIT,
    extraire_texte_par_type_mime,
)
from import_zip import extraire_membres_zip

TAILLE_MAX_ZIP_CHAT_OCTETS = 50 * 1024 * 1024  # 50 Mo -- au-delà de document-chat (15 Mo, un seul fichier), en dessous d'un multiple arbitraire, une archive contenant plusieurs documents doit passer
NOMBRE_MAX_FICHIERS_ZIP_CHAT = 20  # aligné sur la limite de fichiers par upload de Claude.ai (chat)

NOM_OUTIL_DEZIP = "dezipper_zip_chat"

# Extensions lisibles en texte brut sans bibliothèque dédiée (au-delà de
# TYPES_DOCUMENTS_AUTORISES qui couvre pdf/docx/xlsx) -- code source,
# notes, données tabulaires simples.
EXTENSIONS_TEXTE_BRUT = {
    ".txt", ".md", ".csv", ".json", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".yml", ".yaml", ".xml", ".log",
}

_JOBS: dict[str, dict] = {}
_VERROU = threading.Lock()


def _nom_lisible_pour_membre(nom_zip: str, sous_chemin: tuple) -> str:
    chaine = [nom_zip] + [f"{segment}.zip" for segment in sous_chemin]
    if len(chaine) == 1:
        return f"Dézipage de {chaine[0]}"
    parents = ", dans ".join(reversed(chaine[:-1]))
    return f"Dézipage de {chaine[-1]}, dans {parents}"


def _extraire_texte_membre(nom_fichier: str, contenu: bytes, type_mime: str) -> tuple[str | None, str | None]:
    """Renvoie (texte, raison_echec). texte=None si illisible -- raison
    donnée pour que le LLM puisse l'expliquer lui-même à l'étudiant
    plutôt qu'un message d'erreur système générique."""
    try:
        if type_mime in TYPES_DOCUMENTS_AUTORISES:
            texte = extraire_texte_par_type_mime(contenu, type_mime)
        elif any(nom_fichier.lower().endswith(ext) for ext in EXTENSIONS_TEXTE_BRUT):
            texte = contenu.decode("utf-8", errors="strict")
        else:
            return None, "TYPE_NON_PRIS_EN_CHARGE"
    except UnicodeDecodeError:
        return None, "ENCODAGE_ILLISIBLE"
    except Exception as e:
        logging.warning(f"ZIP CHAT : extraction échouée pour {nom_fichier} : {e}")
        return None, "ECHEC_EXTRACTION"

    texte = (texte or "").strip()
    if not texte:
        return None, "AUCUN_TEXTE_TROUVE"
    if len(texte) > LONGUEUR_MAX_TEXTE_EXTRAIT:
        texte = texte[:LONGUEUR_MAX_TEXTE_EXTRAIT]
    return texte, None


def _executer(job_id: str, contenu_zip: bytes, nom_zip: str) -> None:
    job = _JOBS[job_id]
    try:
        membres, erreurs = extraire_membres_zip(contenu_zip, nom_zip)

        membres_traites = membres[:NOMBRE_MAX_FICHIERS_ZIP_CHAT]
        nombre_ignores = len(membres) - len(membres_traites)

        for membre in membres_traites:
            texte, raison_echec = _extraire_texte_membre(
                membre["nom_fichier"], membre["contenu"], membre["type_mime"]
            )
            element = {
                "sous_chemin": membre["sous_chemin"],
                "nom_fichier": membre["nom_fichier"],
                "nom_lisible": _nom_lisible_pour_membre(nom_zip, membre["sous_chemin"]),
                "texte": texte,
                "raison_echec": raison_echec,
            }
            with _VERROU:
                job["elements"].append(element)

        for erreur in erreurs:
            with _VERROU:
                job["elements"].append({
                    "sous_chemin": (),
                    "nom_fichier": erreur["nom"],
                    "nom_lisible": _nom_lisible_pour_membre(nom_zip, ()),
                    "texte": None,
                    "raison_echec": erreur["raison"],
                })

        with _VERROU:
            job["nombre_ignores_limite"] = nombre_ignores
    except Exception as e:
        logging.error(f"ZIP CHAT : dézipage échoué pour {nom_zip} : {e}")
        with _VERROU:
            job["erreur_globale"] = "ZIP_ILLISIBLE"
    finally:
        with _VERROU:
            job["termine"] = True


def demarrer_extraction_zip_chat(contenu: bytes, nom_zip: str) -> str:
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {
        "nom_zip": nom_zip,
        "elements": [],
        "termine": False,
        "erreur_globale": None,
        "nombre_ignores_limite": 0,
    }
    threading.Thread(target=_executer, args=(job_id, contenu, nom_zip), daemon=True).start()
    return job_id


def iterer_statuts(job_id: str):
    """Générateur SYNCHRONE (chat() est lui-même un générateur sync,
    consommé dans un thread de streaming -- voir api/chat.py) : reprend
    la progression du job là où le thread de fond en est, et streame un
    couple statut/statut_termine par élément déjà connu, jusqu'à ce que
    le job soit terminé. Si le job est déjà fini, boucle une seule fois
    sur les éléments déjà là, sans latence -- comportement identique que
    le dézipage ait fini avant ou après l'envoi du message."""
    job = _JOBS.get(job_id)
    if job is None:
        return

    index_connu = 0
    while True:
        with _VERROU:
            nouveaux = list(job["elements"][index_connu:])
            termine = job["termine"]
        for element in nouveaux:
            id_appel = f"zip-{job_id}-{index_connu}"
            index_connu += 1
            yield {
                "type": "statut",
                "texte": f"{element['nom_lisible']}...",
                "id_appel": id_appel,
                "nom_outil": NOM_OUTIL_DEZIP,
                "nom_lisible": element["nom_lisible"],
            }
            yield {
                "type": "statut_termine",
                "texte": f"{element['nom_lisible']} effectuée",
                "id_appel": id_appel,
            }
        if termine:
            break
        time.sleep(0.2)


def obtenir_etat(job_id: str) -> dict | None:
    return _JOBS.get(job_id)


def construire_digest_zip(job_id: str) -> str:
    """Sommaire textuel injecté dans le message envoyé au modèle : liste
    des fichiers avec une référence stable ("job_id::index") que
    gerer_fichier_conversation (action "lire") peut résoudre à la
    demande. Les fichiers non lisibles restent listés avec leur raison
    -- au modèle de le dire lui-même à l'étudiant plutôt qu'une erreur
    système."""
    job = _JOBS.get(job_id)
    if job is None:
        return ""
    if job.get("erreur_globale"):
        return f"[Archive « {job['nom_zip']} » illisible, impossible de l'ouvrir.]"

    lignes = [f"[Contenu de l'archive « {job['nom_zip']} » :]"]
    for index, element in enumerate(job["elements"]):
        chemin_affiche = "/".join(element["sous_chemin"] + (element["nom_fichier"],))
        if element["texte"] is not None:
            reference = f"{job_id}::{index}"
            lignes.append(f"- {chemin_affiche} (référence à donner à gerer_fichier_conversation action=\"lire\" : {reference})")
        else:
            lignes.append(f"- {chemin_affiche} : illisible ({element['raison_echec']})")
    if job.get("nombre_ignores_limite"):
        lignes.append(f"({job['nombre_ignores_limite']} fichier(s) supplémentaire(s) au-delà de la limite de {NOMBRE_MAX_FICHIERS_ZIP_CHAT}, non traités.)")
    return "\n".join(lignes)


def lire_element(reference: str) -> str | None:
    """Résout une référence "job_id::index" donnée par construire_digest_zip
    et renvoie le texte déjà extrait, ou None si introuvable/illisible."""
    try:
        job_id, index_str = reference.split("::", 1)
        index = int(index_str)
    except (ValueError, AttributeError):
        return None
    job = _JOBS.get(job_id)
    if job is None or index < 0 or index >= len(job["elements"]):
        return None
    return job["elements"][index]["texte"]
