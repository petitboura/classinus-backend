"""Outils MCP Higgsfield par l'API (clé partagée) : vidéo, image, prix, annulation.

Enregistrés seulement si une clé API Higgsfield est configurée. Génération en
deux temps (lancer puis consulter), comme la vidéo fal.ai : une génération n'est
jamais instantanée. Le catalogue des modèles est dans core/higgsfield_catalogue.py.
"""
import json
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
            # JSON {"videos": [...]} : détecté génériquement pour afficher
            # les cartes vidéo sous la réponse, comme rechercher_video.
            return json.dumps({"videos": [{"titre": titre.strip() or nom, "url": url}]}, ensure_ascii=False)
        extension = _extension_image(url)
        nom = (titre.strip() or f"Image_Higgsfield_{request_id}") + f".{extension}"
        _sauvegarder_generation_bibliotheque(ctx, url, nom, _MIME_IMAGES[extension])
        # JSON {"images": [...]} : détecté génériquement pour afficher
        # la galerie sous la réponse, comme rechercher_image.
        return json.dumps({"images": [{"titre": titre.strip() or nom, "url": url}]}, ensure_ascii=False)
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
        Version Classinus de Higgsfield (API de Classinus, clé partagée, sans connexion de l'utilisateur). Voie API : elle passe toujours en premier pour la vidéo et l'image. Le compte Higgsfield personnel de l'utilisateur, s'il en a connecté un, n'est ni utilisé ni modifié par cet outil.
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
        Si l'utilisateur a joint un fichier image, vidéo ou son dans cette
        conversation, son lien réel (visible dans le message) peut servir
        de image_url, image_fin_url ou référence.
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
        """Version Classinus de Higgsfield (API de Classinus) : vérifie une vidéo Higgsfield lancée et l'enregistre dans la bibliothèque Classinus sous le titre fourni quand elle est prête. Gère aussi l'échec, le refus de contenu et l'annulation. Vidéo prête : son lien part en JSON et s'affiche tout seul en carte sous ta réponse, présente-la juste brièvement en texte."""
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
        Si l'utilisateur a joint une image dans cette conversation, son
        lien réel (visible dans le message) peut servir de référence.
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
        """Vérifie une image Higgsfield lancée et l'enregistre dans la bibliothèque Classinus sous le titre fourni quand elle est prête. Gère aussi l'échec, le refus de contenu et l'annulation. Image prête : son lien part en JSON et s'affiche tout seul en galerie sous ta réponse, présente-la juste brièvement en texte."""
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
        Mêmes liens de fichiers joints acceptés que lancer_video_higgsfield.
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
            # Estimation toujours en credits, jamais en argent (31/10/2026).
            return f"Coût estimé : {prix['credits']} crédits."
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


# Fonctions MCP-only (31/10/2026) : enregistrees meme sans cle API, car leur
# voie est notre MCP partage, pas l'API. Chaque appel verifie en direct la
# configuration et l'etat du compte partage avant de depenser quoi que ce soit.

@mcp_generation.tool()
def lister_capacites_higgsfield(ctx: Context = None) -> str:
    """
    Liste les capacités Higgsfield de Classinus et leur voie réelle : API
    d'abord (vidéo, image), notre MCP partagé ensuite pour les fonctions
    absentes de l'API (audio, 3D, édition, studios). À appeler avant toute
    génération spéciale pour savoir ce qui est faisable, quels médias sont
    requis, et quels outils MCP existent vraiment en ce moment (vérifié en
    direct, avec leur schéma d'arguments). Le compte Higgsfield personnel
    de l'utilisateur n'est ni utilisé ni modifié.
    """
    try:
        from connexions.higgsfield_mcp import etat_service
        from core.generation_video_higgsfield import higgsfield_api_disponible as _api_ok
        from core.higgsfield_capacites import CAPACITES
        from core.higgsfield_mcp_partage import lister_outils_partages
        from core.higgsfield_routeur import choisir_voie

        etat = etat_service()
        outils_mcp = []
        if etat["connecte"]:
            try:
                outils_mcp = lister_outils_partages()
            except Exception:
                outils_mcp = []
        noms_mcp = {o["nom"] for o in outils_mcp}
        lignes = []
        for capacite in CAPACITES:
            choix = choisir_voie(capacite["id"], _api_ok(), etat["connecte"])
            ligne = {
                "capacite": capacite["id"],
                "label": capacite["label"],
                "voie": choix["voie"],
                "raison": choix["raison"],
                "medias_requis": capacite["medias_requis"],
            }
            if capacite["voie"] == "mcp":
                presents = [n for n in capacite["outils_mcp"] if n in noms_mcp]
                ligne["outils_mcp_disponibles"] = presents
                if choix["voie"] == "mcp" and not presents:
                    ligne["voie"] = "indisponible"
                    ligne["raison"] = "Aucun outil de cette fonction n'est exposé par le MCP en ce moment."
            lignes.append(ligne)
        return json.dumps({
            "api_configuree": _api_ok(),
            "mcp_partage": etat,
            "capacites": lignes,
            "outils_mcp": outils_mcp,
        }, ensure_ascii=False)
    except Exception as e:
        return _message_erreur(e, "lister les capacités Higgsfield")


@mcp_generation.tool()
def generer_mcp_higgsfield(
    capacite: str,
    outil: str,
    arguments_json: str,
    titre: str,
    ctx: Context = None,
) -> str:
    """
    Lance une fonction Higgsfield disponible uniquement via notre MCP
    partagé (audio, 3D, édition, studios) : l'API ne sait pas la faire, il
    n'y a aucun équivalent API. `capacite` : un identifiant de
    lister_capacites_higgsfield (ex. audio_tts, upscale_video, doublage).
    `outil` : un nom présent dans outils_mcp_disponibles de cette capacité.
    `arguments_json` : objet JSON conforme au schéma de cet outil (voir
    lister_capacites_higgsfield), avec les adresses https des médias requis.
    `titre` : nom court du résultat, sans extension. Génération payante sur
    le compte partagé de Classinus, comptée dans la limite MCP du jour de
    l'utilisateur. N'utilise jamais le compte Higgsfield personnel de
    l'utilisateur. Si la capacité est servie par l'API (vidéo, image),
    refuse et renvoie vers lancer_video_higgsfield ou generer_image_higgsfield.
    """
    try:
        from core.higgsfield_capacites import capacite_par_id
        from core.higgsfield_mcp_partage import appeler_outil_partage
        from core.higgsfield_routeur import choisir_voie
        from connexions.higgsfield_mcp import etat_service

        infos = capacite_par_id(capacite)
        if infos is None:
            return "Erreur : capacité Higgsfield inconnue. Appelle lister_capacites_higgsfield d'abord."
        if infos["voie"] == "api":
            return (
                "Erreur : cette capacité passe par l'API Classinus, pas par le MCP. "
                "Utilise lancer_video_higgsfield ou generer_image_higgsfield."
            )
        if (outil or "").strip() not in infos["outils_mcp"]:
            return (
                f"Erreur : l'outil {outil} n'appartient pas à la capacité {capacite}. "
                f"Outils possibles : {', '.join(infos['outils_mcp'])}."
            )
        try:
            arguments = json.loads(arguments_json or "{}")
        except ValueError:
            return "Erreur : arguments_json n'est pas un JSON valide."
        if not isinstance(arguments, dict):
            return "Erreur : arguments_json doit être un objet JSON."
        choix = choisir_voie(capacite, False, etat_service()["connecte"])
        if choix["voie"] != "mcp":
            return f"Indisponible : {choix['raison']}"
        reserver_generation(_supabase_memoire, _id_utilisateur(ctx), "mcp")
        texte = appeler_outil_partage(outil, arguments)
        return texte
    except Exception as e:
        return _message_erreur(e, "lancer cette fonction MCP Higgsfield")


@mcp_generation.tool()
def etat_mcp_partage_higgsfield(ctx: Context = None) -> str:
    """
    Santé du MCP Higgsfield partagé de Classinus (fonctions MCP-only) :
    configuré ou non, connecté ou à reconnecter, et outils MCP-only
    réellement exposés en ce moment. Lecture seule, ne dépense rien.
    À utiliser si une fonction MCP échoue ou pour vérifier avant de promettre.
    """
    try:
        from connexions.higgsfield_mcp import etat_service
        from core.higgsfield_mcp_partage import lister_outils_partages

        etat = etat_service()
        outils = []
        if etat["connecte"]:
            outils = [o["nom"] for o in lister_outils_partages()]
        return json.dumps({"mcp_partage": etat, "outils_mcp_only_disponibles": outils}, ensure_ascii=False)
    except Exception as e:
        return _message_erreur(e, "vérifier le MCP Higgsfield partagé")
