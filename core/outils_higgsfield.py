"""Outils MCP Higgsfield par l'API (clé partagée) : vidéo, image, prix, annulation.

Enregistrés seulement si une clé API Higgsfield est configurée. Génération en
deux temps (lancer puis consulter), comme la vidéo fal.ai : une génération n'est
jamais instantanée. Le catalogue des modèles est dans core/higgsfield_catalogue.py.
"""
import logging
from typing import List, Optional

from core.generation_video_higgsfield import (
    annuler_generation,
    estimer_cout,
    higgsfield_api_disponible,
    lancer_generation,
    statut_generation,
)
from core.higgsfield_requetes import (
    ErreurHiggsfield,
    construire_requete_image,
    construire_requete_video,
)
from core.higgsfield_limites import reserver_generation
from core.outils_generation_commun import (
    mcp_generation,
    Context,
    _sauvegarder_generation_bibliotheque,
    _supabase_memoire,
)

_MIME_IMAGES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


def _extension_image(url: str) -> str:
    fin = url.split("?", 1)[0].rsplit(".", 1)[-1].lower()
    return fin if fin in _MIME_IMAGES else "png"


def _id_utilisateur(ctx):
    try:
        return ctx.request_context.request.query_params.get("user_id")
    except Exception:
        return None


def _message_erreur(e: Exception, action: str) -> str:
    if isinstance(e, ErreurHiggsfield):
        return f"Erreur : {e}"
    logging.error("ERREUR Higgsfield (%s) : %s", action, e)
    return f"Erreur : impossible de {action}, réessaie."


def _texte_suivi(request_id: str, titre: str, genre: str, ctx) -> str:
    """Suivi commun vidéo et image : enregistre le fichier en bibliothèque quand c'est prêt."""
    resultat = statut_generation(request_id)
    etat = resultat["etat"]
    if etat == "terminee":
        url = resultat["url"]
        if not url:
            return "La génération est terminée mais le fichier n'est pas encore disponible, redemande dans un instant."
        if genre == "video":
            nom, mime = (titre.strip() or f"Video_Higgsfield_{request_id}") + ".mp4", "video/mp4"
            _sauvegarder_generation_bibliotheque(ctx, url, nom, mime)
            return f"Vidéo terminée et enregistrée dans la bibliothèque : {url}"
        extension = _extension_image(url)
        nom = (titre.strip() or f"Image_Higgsfield_{request_id}") + f".{extension}"
        _sauvegarder_generation_bibliotheque(ctx, url, nom, _MIME_IMAGES[extension])
        return f"Image terminée et enregistrée dans la bibliothèque : {url}"
    if etat == "echec":
        raison = f" ({resultat['erreur']})" if resultat["erreur"] else ""
        return (
            f"La génération a échoué{raison}. Elle n'est pas facturée. "
            "Dis-le à l'utilisateur et propose de relancer avec une description différente."
        )
    if etat == "bloquee":
        return (
            "Higgsfield a refusé ce contenu (non autorisé). Elle n'est pas facturée. "
            "Ne relance pas la même description : propose-en une autre à l'utilisateur."
        )
    if etat == "annulee":
        return "Cette génération a été annulée, il n'y a plus rien à attendre."
    return "Toujours en cours. Redemande le suivi dans une minute, sans bloquer l'utilisateur."


if higgsfield_api_disponible():
    @mcp_generation.tool()
    def lancer_video_higgsfield(
        prompt: str,
        titre: str,
        modele: str = "seedance",
        duree_secondes: int = 5,
        format_video: str = "",
        qualite: str = "",
        son: bool = True,
        image_url: str = "",
        image_fin_url: str = "",
        images_reference: Optional[List[str]] = None,
        videos_reference: Optional[List[str]] = None,
        sons_reference: Optional[List[str]] = None,
        ctx: Context = None,
    ) -> str:
        """
        Version Classinus de Higgsfield (API de Classinus, clé partagée, sans connexion de l'utilisateur). Si l'utilisateur a connecté son propre compte Higgsfield, ses outils higgsfield_ passent en premier.
        Lance une vidéo Higgsfield : depuis une description, en animant une
        image si `image_url` est donné, ou guidée par des références. NE renvoie PAS la vidéo (1 à 3 minutes) :
        renvoie un identifiant à donner à consulter_video_higgsfield un peu plus
        tard. Préviens l'utilisateur que ça prend du temps.

        `titre` (obligatoire) : nom court et clair de la vidéo, sans extension.
        Redonne EXACTEMENT le même titre à consulter_video_higgsfield.

        `modele` : "seedance" (par défaut) ou "kling". Garde seedance sauf si
        l'utilisateur demande autre chose. `duree_secondes` : 4 à 15 pour
        seedance, 3 à 15 pour kling. `format_video` : "16:9", "9:16" (téléphone)
        ou "1:1", seedance accepte aussi "4:3", "3:4", "21:9". Ignoré si une image
        de départ est donnée (le cadrage suit l'image). `qualite` (seedance
        seulement) : "480p", "720p", "1080p" ou "4k", plus c'est haut plus c'est
        cher : laisse vide sauf demande. `son` : avec ou sans son.

        `image_url` : adresse publique (https) de l'image à animer. `image_fin_url` :
        adresse publique de la dernière image, la vidéo fait la transition.

        RÉFÉRENCES (seedance seulement, ne se mélange pas avec image_url) :
        `images_reference` (9 maximum), `videos_reference` (3 maximum),
        `sons_reference` (3 maximum), toutes en adresses publiques https. Pour
        garder le MÊME personnage ou le même style d'une vidéo à l'autre, redonne
        à chaque fois les mêmes images de référence. Des sons seuls ne suffisent
        pas : il faut au moins une image ou une vidéo.
        Règles officielles de Higgsfield sur les références : chaque vidéo de
        référence est coupée à 15 secondes, et les sons sont ramenés à 2 à 15
        secondes par fichier, 15 secondes au total. Si une vidéo ou un son de
        l'étudiant est plus long, dis-le-lui avant de lancer et propose de ne
        garder que le passage utile.

        Chaque utilisateur a un nombre limité de générations par jour. Génération
        payante : si l'utilisateur hésite, appelle d'abord estimer_cout_higgsfield.
        """
        try:
            adresse, corps = construire_requete_video(
                modele, prompt, duree_secondes, format_video, qualite, son, image_url, image_fin_url,
                images_reference, videos_reference, sons_reference,
            )
            reserver_generation(_supabase_memoire, _id_utilisateur(ctx), "video")
            resultat = lancer_generation(adresse, corps)
            return (
                f"Génération Higgsfield lancée (id: {resultat['request_id']}). "
                f"Utilise ensuite consulter_video_higgsfield avec cet identifiant et le même titre ({titre})."
            )
        except Exception as e:
            return _message_erreur(e, "lancer la génération vidéo")

    @mcp_generation.tool()
    def consulter_video_higgsfield(request_id: str, titre: str, ctx: Context = None) -> str:
        """Version Classinus de Higgsfield (API de Classinus) : vérifie une vidéo Higgsfield lancée et l'enregistre dans la bibliothèque Classinus sous le titre fourni quand elle est prête. Gère aussi l'échec, le refus de contenu et l'annulation."""
        try:
            return _texte_suivi(request_id, titre, "video", ctx)
        except Exception as e:
            return _message_erreur(e, "consulter cette génération vidéo")

    @mcp_generation.tool()
    def generer_image_higgsfield(
        prompt: str,
        titre: str,
        modele: str = "grok",
        format_image: str = "auto",
        qualite: str = "1k",
        images_reference: Optional[List[str]] = None,
        ctx: Context = None,
    ) -> str:
        """
        Lance une image Higgsfield : depuis une description, ou en modifiant des
        images existantes si `images_reference` est donné (adresses publiques https,
        10 maximum). Renvoie un identifiant à donner à consulter_image_higgsfield
        dans quelques secondes.

        `titre` (obligatoire) : nom court et clair de l'image, sans extension.
        Redonne EXACTEMENT le même titre à consulter_image_higgsfield.

        `format_image` : "auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
        "2:1" ou "1:2". `qualite` : "1k" ou "2k". Génération payante, avec un
        nombre limité par jour et par utilisateur. Pour garder le même personnage
        d'une image à l'autre, redonne la même image de référence.
        """
        try:
            adresse, corps = construire_requete_image(modele, prompt, format_image, qualite, images_reference)
            reserver_generation(_supabase_memoire, _id_utilisateur(ctx), "image")
            resultat = lancer_generation(adresse, corps)
            return (
                f"Génération d'image Higgsfield lancée (id: {resultat['request_id']}). "
                f"Utilise ensuite consulter_image_higgsfield avec cet identifiant et le même titre ({titre})."
            )
        except Exception as e:
            return _message_erreur(e, "lancer la génération d'image")

    @mcp_generation.tool()
    def consulter_image_higgsfield(request_id: str, titre: str, ctx: Context = None) -> str:
        """Vérifie une image Higgsfield lancée et l'enregistre dans la bibliothèque Classinus sous le titre fourni quand elle est prête. Gère aussi l'échec, le refus de contenu et l'annulation."""
        try:
            return _texte_suivi(request_id, titre, "image", ctx)
        except Exception as e:
            return _message_erreur(e, "consulter cette génération d'image")

    @mcp_generation.tool()
    def estimer_cout_higgsfield(
        genre: str,
        prompt: str,
        modele: str = "",
        duree_secondes: int = 5,
        format_video: str = "",
        qualite: str = "",
        son: bool = True,
        image_url: str = "",
        images_reference: Optional[List[str]] = None,
    ) -> str:
        """
        Donne le prix d'une génération Higgsfield AVANT de la lancer (rien n'est
        consommé). `genre` : "video" ou "image". Mêmes réglages que
        lancer_video_higgsfield (modèles vidéo : seedance, kling ; image : grok).
        À utiliser pour comparer deux réglages ou avant une vidéo longue ou en
        haute qualité. Si le coût paraît élevé, propose un réglage moins cher.
        """
        try:
            if (genre or "").strip().lower() == "image":
                adresse, corps = construire_requete_image(modele, prompt, format_video, qualite, images_reference)
            else:
                adresse, corps = construire_requete_video(
                    modele, prompt, duree_secondes, format_video, qualite, son, image_url, "",
                    images_reference,
                )
            prix = estimer_cout(adresse, corps)
            return f"Coût estimé : {prix['credits']} crédits (environ {prix['usd']} dollars)."
        except Exception as e:
            return _message_erreur(e, "estimer le coût")

    @mcp_generation.tool()
    def annuler_generation_higgsfield(request_id: str) -> str:
        """Annule une génération Higgsfield (vidéo ou image) tant qu'elle est encore en attente. Les crédits sont alors rendus. Impossible une fois qu'elle a commencé."""
        try:
            if annuler_generation(request_id):
                return "Génération annulée. Les crédits sont rendus."
            return "Impossible d'annuler : la génération a déjà commencé, elle va se terminer."
        except Exception as e:
            return _message_erreur(e, "annuler cette génération")
