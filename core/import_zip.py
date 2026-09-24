"""
Import de fichiers .zip dans la bibliothèque personnelle (23/09/2026,
demande Bourama : avant cette date, un zip uploadé était stocké tel
quel, jamais extrait -- explicitement listé comme type "réellement non
extractible" dans core/file_attente_vectorisation.py:necessite_
vectorisation_fichier_privee).

Principe : un .zip uploadé n'est plus stocké tel quel. Il est déplié --
chaque fichier à l'intérieur est enregistré INDIVIDUELLEMENT via
enregistrer_fichier, exactement comme s'il avait été uploadé seul (donc
lisible/vectorisable normalement selon son propre type), et rangé dans
un nouveau dossier nommé d'après le zip -- même principe qu'un import
de dossier complet depuis l'ordinateur (déjà supporté par le
navigateur/frontend, voir EspaceBibliotheque.tsx). Un zip imbriqué dans
le zip est déplié récursivement, dans un sous-dossier.

Volontairement dans son propre fichier plutôt que dans bibliotheque_
fichiers.py ou extraction_contenu.py (demande Bourama : "qu'un fichier
ne grossisse pas bêtement") -- module dédié, appelé par les endpoints
d'upload concernés.

Étape 1/23-09 : bibliothèque privée uniquement (et donc le chat, qui
utilise le même endpoint POST /api/bibliotheque). Bibliothèque publique
et dossiers désignés (téléphone) ont leurs propres systèmes de dossiers
(core/dossiers_catalogue_public.py, core/dossiers_designes_mobile.py)
et ne sont pas encore branchés sur ce module -- prochaine étape.
"""

import io
import logging
import mimetypes
import zipfile

from postgrest.exceptions import APIError

from bibliotheque_fichiers import enregistrer_fichier
from dossiers_bibliotheque import creer_dossier, ranger_fichier
from file_attente_vectorisation import necessite_vectorisation_fichier_privee

# Entrées à ignorer systématiquement dans un zip : métadonnées macOS,
# fichiers cachés du système -- jamais un vrai document de l'utilisateur.
SEGMENTS_IGNORES = {"__MACOSX", ".DS_Store"}

EXTENSIONS_ZIP = (".zip",)
TYPES_MIME_ZIP = ("application/zip", "application/x-zip-compressed", "application/zip-compressed")


def est_zip(nom_fichier: str, type_mime: str | None) -> bool:
    """Détecte un zip par extension ou type MIME (les deux sont peu fiables séparément selon le client qui upload)."""
    return (nom_fichier or "").lower().endswith(EXTENSIONS_ZIP) or (type_mime in TYPES_MIME_ZIP)


def _type_mime_deduit(nom_fichier: str) -> str:
    type_mime, _ = mimetypes.guess_type(nom_fichier)
    return type_mime or "application/octet-stream"


def extraire_membres_zip(contenu_zip: bytes, nom_zip: str, sous_chemin: tuple = ()) -> tuple[list[dict], list[dict]]:
    """
    Fonction bas niveau, PURE (aucune écriture) : extrait récursivement
    les fichiers d'un zip -- un zip imbriqué est déplié dans un
    "sous_chemin" nommé d'après lui (tuple de noms de dossiers virtuels,
    depuis la racine du zip donné), jamais stocké tel quel.

    Partagée par les 3 bibliothèques (privée, publique, dossiers
    désignés) qui ont chacune leur propre notion de "dossier" -- reste
    volontairement à ce qu'il y a de commun (lister/lire les octets),
    chaque appelant restant responsable d'enregistrer chaque membre
    selon son propre modèle (voir deplier_zip_bibliotheque et
    deplier_zip_bibliotheque_publique ci-dessous pour la privée/publique ;
    api/dossiers_designes.py pour les dossiers désignés, qui utilise
    directement cette fonction -- son "dossier" est juste un chemin,
    pas une ligne à créer).

    Renvoie (membres, erreurs) : chaque membre est {"sous_chemin":
    tuple[str], "nom_fichier": str, "contenu": bytes, "type_mime": str}.
    """
    membres = []
    erreurs = []

    try:
        archive = zipfile.ZipFile(io.BytesIO(contenu_zip))
    except zipfile.BadZipFile:
        erreurs.append({"nom": nom_zip, "raison": "ZIP_ILLISIBLE"})
        return membres, erreurs

    for info in archive.infolist():
        if info.is_dir():
            continue

        chemin_membre = info.filename.replace("\\", "/")
        nom_membre = chemin_membre.rsplit("/", 1)[-1]

        if not nom_membre or nom_membre.startswith(".") or any(seg in SEGMENTS_IGNORES for seg in chemin_membre.split("/")):
            continue

        try:
            contenu_membre = archive.read(info)
        except Exception:
            logging.warning(f"IMPORT ZIP : lecture échouée pour {chemin_membre} dans {nom_zip}")
            erreurs.append({"nom": nom_membre, "raison": "LECTURE_ECHOUEE"})
            continue

        if len(contenu_membre) == 0:
            continue

        type_mime_membre = _type_mime_deduit(nom_membre)

        if est_zip(nom_membre, type_mime_membre):
            nom_sous_dossier = nom_membre.rsplit(".", 1)[0] if nom_membre.lower().endswith(".zip") else nom_membre
            sous_membres, sous_erreurs = extraire_membres_zip(contenu_membre, nom_membre, sous_chemin + (nom_sous_dossier,))
            membres.extend(sous_membres)
            erreurs.extend(sous_erreurs)
            continue

        membres.append({
            "sous_chemin": sous_chemin,
            "nom_fichier": nom_membre,
            "contenu": contenu_membre,
            "type_mime": type_mime_membre,
        })

    return membres, erreurs


def deplier_zip_bibliotheque(
    contenu_zip: bytes,
    nom_zip: str,
    niveau: str,
    uploade_par: str,
    user_id: str = None,
    agent_id: str = None,
    origine: str = "bibliotheque",
    dossier_parent_id: str = None,
) -> dict:
    """
    Déplie un zip dans la bibliothèque personnelle de user_id. Ne
    déclenche PAS la vectorisation elle-même (voir statut_vectorisation
    de chaque ligne renvoyée dans "fichiers") -- c'est à l'appelant (la
    route API, contexte async) de créer les tâches de fond, comme pour
    un upload classique dans api/bibliotheque_utilisateur.py.

    Un fichier en échec (nom déjà utilisé dans la bibliothèque, contenu
    illisible du zip...) est ignoré et signalé dans "erreurs", sans
    bloquer l'import des autres fichiers du zip.

    Renvoie {"dossier": <ligne dossier créée>, "fichiers": [<lignes
    fichiers créées avec succès>], "erreurs": [{"nom": str, "raison": str}]}.
    """
    nom_dossier = nom_zip.rsplit(".", 1)[0] if nom_zip.lower().endswith(".zip") else nom_zip
    dossier = creer_dossier(user_id, nom_dossier, dossier_parent_id)

    fichiers_crees = []
    erreurs = []

    try:
        archive = zipfile.ZipFile(io.BytesIO(contenu_zip))
    except zipfile.BadZipFile:
        erreurs.append({"nom": nom_zip, "raison": "ZIP_ILLISIBLE"})
        return {"dossier": dossier, "fichiers": fichiers_crees, "erreurs": erreurs}

    for info in archive.infolist():
        if info.is_dir():
            continue

        chemin_membre = info.filename.replace("\\", "/")
        nom_membre = chemin_membre.rsplit("/", 1)[-1]

        if not nom_membre or nom_membre.startswith(".") or any(seg in SEGMENTS_IGNORES for seg in chemin_membre.split("/")):
            continue

        try:
            contenu_membre = archive.read(info)
        except Exception:
            logging.warning(f"IMPORT ZIP : lecture échouée pour {chemin_membre} dans {nom_zip}")
            erreurs.append({"nom": nom_membre, "raison": "LECTURE_ECHOUEE"})
            continue

        if len(contenu_membre) == 0:
            continue

        type_mime_membre = _type_mime_deduit(nom_membre)

        # Zip imbriqué : déplié récursivement dans un sous-dossier, pas stocké tel quel.
        if est_zip(nom_membre, type_mime_membre):
            sous_resultat = deplier_zip_bibliotheque(
                contenu_membre,
                nom_membre,
                niveau=niveau,
                uploade_par=uploade_par,
                user_id=user_id,
                agent_id=agent_id,
                origine=origine,
                dossier_parent_id=dossier["id"],
            )
            fichiers_crees.extend(sous_resultat["fichiers"])
            erreurs.extend(sous_resultat["erreurs"])
            continue

        try:
            ligne = enregistrer_fichier(
                contenu=contenu_membre,
                nom_fichier=nom_membre,
                type_mime=type_mime_membre,
                niveau=niveau,
                uploade_par=uploade_par,
                agent_id=agent_id,
                user_id=user_id,
                description=nom_membre,
                origine=origine,
                statut_vectorisation="en_attente" if necessite_vectorisation_fichier_privee(type_mime_membre, nom_membre) else "pret",
            )
        except APIError as e:
            raison = "NOM_DEJA_UTILISE" if getattr(e, "code", None) == "23505" else "ECHEC_STOCKAGE"
            logging.warning(f"IMPORT ZIP : échec enregistrement {nom_membre} depuis {nom_zip} ({raison})")
            erreurs.append({"nom": nom_membre, "raison": raison})
            continue
        except Exception:
            logging.warning(f"IMPORT ZIP : échec enregistrement {nom_membre} depuis {nom_zip}")
            erreurs.append({"nom": nom_membre, "raison": "ECHEC_STOCKAGE"})
            continue

        ranger_fichier(ligne["id"], dossier["id"])
        fichiers_crees.append(ligne)

    return {"dossier": dossier, "fichiers": fichiers_crees, "erreurs": erreurs}


def deplier_zip_bibliotheque_publique(
    contenu_zip: bytes,
    nom_zip: str,
    ajoute_par: str,
    dossier_parent_id: str = None,
    pays=None, niveau=None, categorie=None, classe=None, specialite=None,
) -> dict:
    """
    Équivalent de deplier_zip_bibliotheque, pour le catalogue public
    (23/09/2026, étape 2 -- même chantier). Chaque fichier du zip est
    publié individuellement via core.catalogue_public_publication.
    publier_fichier_public (déjà le point d'entrée prévu pour publier un
    fichier dont les octets sont déjà en main, hors requête HTTP directe --
    voir sa docstring), rangé dans un nouveau dossier du catalogue public
    nommé d'après le zip. Ne déclenche pas non plus la vectorisation/
    extraction elle-même -- à l'appelant (route API) de créer les tâches
    de fond pour chaque entrée renvoyée, comme pour un upload classique.
    """
    from core.catalogue_public_publication import publier_fichier_public
    from core.dossiers_catalogue_public import creer_dossier as creer_dossier_public

    nom_dossier = nom_zip.rsplit(".", 1)[0] if nom_zip.lower().endswith(".zip") else nom_zip
    dossier = creer_dossier_public(
        ajoute_par, nom_dossier, dossier_parent_id=dossier_parent_id,
        pays=pays, niveau=niveau, categorie=categorie, classe=classe, specialite=specialite,
    )

    fichiers_crees = []
    erreurs = []

    try:
        archive = zipfile.ZipFile(io.BytesIO(contenu_zip))
    except zipfile.BadZipFile:
        erreurs.append({"nom": nom_zip, "raison": "ZIP_ILLISIBLE"})
        return {"dossier": dossier, "fichiers": fichiers_crees, "erreurs": erreurs}

    for info in archive.infolist():
        if info.is_dir():
            continue

        chemin_membre = info.filename.replace("\\", "/")
        nom_membre = chemin_membre.rsplit("/", 1)[-1]

        if not nom_membre or nom_membre.startswith(".") or any(seg in SEGMENTS_IGNORES for seg in chemin_membre.split("/")):
            continue

        try:
            contenu_membre = archive.read(info)
        except Exception:
            logging.warning(f"IMPORT ZIP PUBLIC : lecture échouée pour {chemin_membre} dans {nom_zip}")
            erreurs.append({"nom": nom_membre, "raison": "LECTURE_ECHOUEE"})
            continue

        if len(contenu_membre) == 0:
            continue

        type_mime_membre = _type_mime_deduit(nom_membre)

        if est_zip(nom_membre, type_mime_membre):
            sous_resultat = deplier_zip_bibliotheque_publique(
                contenu_membre, nom_membre, ajoute_par=ajoute_par, dossier_parent_id=dossier["id"],
                pays=pays, niveau=niveau, categorie=categorie, classe=classe, specialite=specialite,
            )
            fichiers_crees.extend(sous_resultat["fichiers"])
            erreurs.extend(sous_resultat["erreurs"])
            continue

        try:
            entree = publier_fichier_public(
                ajoute_par=ajoute_par,
                contenu=contenu_membre,
                nom_fichier=nom_membre,
                type_mime=type_mime_membre,
                dossier_id=dossier["id"],
                pays=pays, niveau=niveau, categorie=categorie, classe=classe, specialite=specialite,
            )
        except APIError as e:
            raison = "NOM_DEJA_UTILISE" if getattr(e, "code", None) == "23505" else "ECHEC_STOCKAGE"
            logging.warning(f"IMPORT ZIP PUBLIC : échec publication {nom_membre} depuis {nom_zip} ({raison})")
            erreurs.append({"nom": nom_membre, "raison": raison})
            continue
        except Exception:
            logging.warning(f"IMPORT ZIP PUBLIC : échec publication {nom_membre} depuis {nom_zip}")
            erreurs.append({"nom": nom_membre, "raison": "ECHEC_STOCKAGE"})
            continue

        fichiers_crees.append(entree)

    return {"dossier": dossier, "fichiers": fichiers_crees, "erreurs": erreurs}
