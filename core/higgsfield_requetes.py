"""Construction et vérification des demandes Higgsfield (vidéo et image).

Aucun appel réseau ici : on transforme les choix de l'IA en une demande valide
selon le catalogue (core/higgsfield_catalogue.py). Toute erreur est une
ErreurHiggsfield avec un message lisible, que l'IA peut relayer telle quelle.
"""
from core.higgsfield_catalogue import (
    MODELES_IMAGE,
    MODELES_VIDEO,
    MODELE_IMAGE_DEFAUT,
    MODELE_VIDEO_DEFAUT,
    noms_modeles_image,
    noms_modeles_video,
)


class ErreurHiggsfield(RuntimeError):
    """Erreur dont le message est écrit pour être lu par l'IA, puis par l'utilisateur."""


def _adresse_publique(valeur, libelle: str) -> str:
    texte = (valeur or "").strip()
    if not texte:
        return ""
    if not texte.startswith("https://"):
        raise ErreurHiggsfield(f"{libelle} doit être une adresse publique en https.")
    return texte


def _entier_borne(valeur, mini: int, maxi: int, defaut: int) -> int:
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        nombre = defaut
    return min(max(nombre, mini), maxi)


def _choix_valide(valeur, permises, libelle: str) -> str:
    texte = (valeur or "").strip().lower()
    if not texte:
        return ""
    if texte not in permises:
        raise ErreurHiggsfield(f"{libelle} \"{texte}\" non disponible. Choix possibles : {', '.join(permises)}.")
    return texte


def construire_requete_video(
    modele,
    prompt,
    duree=None,
    format_video="",
    qualite="",
    son=True,
    image_url="",
    image_fin_url="",
):
    """Renvoie (adresse_du_modele, corps_de_la_demande) pour une vidéo."""
    cle = (modele or MODELE_VIDEO_DEFAUT).strip().lower()
    spec = MODELES_VIDEO.get(cle)
    if not spec:
        raise ErreurHiggsfield(f"Modèle vidéo \"{cle}\" inconnu. Modèles disponibles : {noms_modeles_video()}.")

    description = (prompt or "").strip()
    depart = _adresse_publique(image_url, "L'image de départ")
    fin = _adresse_publique(image_fin_url, "L'image de fin")
    if fin and not depart:
        raise ErreurHiggsfield("Une image de fin demande aussi une image de départ.")
    if not description and (not depart or spec["prompt_obligatoire_avec_image"]):
        raise ErreurHiggsfield("Il faut une description pour cette vidéo.")

    mini, maxi = spec["duree"]
    corps = {"duration": _entier_borne(duree, mini, maxi, spec["duree_defaut"])}
    if description:
        corps["prompt"] = description

    if depart:
        # Avec une image de départ, le cadrage suit l'image : pas de choix de format.
        corps["image_url"] = depart
        if fin:
            corps[spec["champ_image_fin"]] = fin
        adresse = spec["image"]
    else:
        adresse = spec["texte"]
        choix_format = _choix_valide(format_video, spec["formats"], "Format")
        if choix_format:
            corps["aspect_ratio"] = choix_format

    if spec["qualites"]:
        choix_qualite = _choix_valide(qualite, spec["qualites"], "Qualité")
        if choix_qualite:
            corps["resolution"] = choix_qualite

    if son is not None:
        corps[spec["champ_son"]] = bool(son) if spec["son_booleen"] else ("on" if son else "off")
    return adresse, corps


def construire_requete_image(modele, prompt, format_image="", qualite="", images_reference=None):
    """Renvoie (adresse_du_modele, corps_de_la_demande) pour une image."""
    cle = (modele or MODELE_IMAGE_DEFAUT).strip().lower()
    spec = MODELES_IMAGE.get(cle)
    if not spec:
        raise ErreurHiggsfield(f"Modèle d'image \"{cle}\" inconnu. Modèles disponibles : {noms_modeles_image()}.")

    description = (prompt or "").strip()
    if not description:
        raise ErreurHiggsfield("Il faut une description pour cette image.")

    corps = {"prompt": description}
    choix_format = _choix_valide(format_image, spec["formats"], "Format")
    if choix_format and choix_format != spec["format_defaut"]:
        corps["aspect_ratio"] = choix_format
    choix_qualite = _choix_valide(qualite, spec["qualites"], "Qualité")
    if choix_qualite:
        corps["resolution"] = choix_qualite

    references = []
    for adresse in images_reference or []:
        propre = _adresse_publique(adresse, "Une image de référence")
        if propre:
            references.append(propre)
    if len(references) > spec["max_references"]:
        raise ErreurHiggsfield(f"Maximum {spec['max_references']} images de référence.")
    if references:
        corps["image_urls"] = references
    return spec["endpoint"], corps
