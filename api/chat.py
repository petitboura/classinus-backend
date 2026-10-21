"""
Route de chat en streaming pour le frontend Next.js (djiguigne-frontend).

Chaînon manquant identifié pendant la migration Streamlit -> Next.js :
jusqu'ici, la fonction chat()
(core/main.py) n'était appelée qu'en interne par chat.py (Streamlit), en
process. Cette route l'expose en HTTP, via Server-Sent Events (SSE), pour
que la nouvelle page de chat React puisse lui parler à distance.

La logique IA elle-même (chat(), dans core/main.py) n'est PAS réécrite ici,
seulement branchée à un vrai endpoint HTTP -- même prompt système, mêmes
outils MCP, même cascade de modèles qu'avant.
"""

import json
import logging
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Literal

from api.auth import utilisateur_optionnel, supabase
from core.video_workspaces import chemin_video, lire_metadonnees_video, workspace_dir
from core.arret_tour import demander_arret_utilisateur, fermer_arret, ouvrir_arret
from core.canal_agent_applicatif import (
    annuler_attentes, debuter_tour, definir_lecture_editeur_chat, diffuser_arret, renvoyer_messages_non_lus,
    retirer_lecture_editeur_chat, terminer_tour,
)
from core.plafond_outils_tour import retirer_plafond_tour
from core.limitation_debit import limiteur
from core.restriction_mineur import acces_chat_bloque_pour_mineur
from main import chat as chat_generateur  # core/main.py:chat()
from fournisseurs_llm import modele_id_est_autorise

logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class OutilHistorique(BaseModel):
    """Un résultat d'outil attaché à un message assistant de l'historique
    (voir core/historique_outils.py) -- même forme que meta.outils déjà
    sauvegardé pour l'affichage (nomOutil/nomLisible/resultat, sans
    sources/images : inutiles pour le modèle, uniquement pour l'UI)."""
    nomOutil: str
    nomLisible: str
    resultat: str


class MessageHistorique(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    # Ajouté 15/09/2026 (demande Bourama) : résultats des outils exécutés
    # pendant CE message assistant (voir ChatIA.tsx:historiquePourApi),
    # réinjectés au modèle au tour suivant -- voir
    # core/historique_outils.py. Absent/vide pour un message user ou un
    # message assistant sans outil, comportement inchangé dans ce cas.
    outils: Optional[List[OutilHistorique]] = None


class Localisation(BaseModel):
    latitude: float
    longitude: float


class RepriseConfirmation(BaseModel):
    etat_reprise: dict
    approuve: bool


class ZoneSelectionVideo(BaseModel):
    """Zone normalisée en coordonnées relatives à l'image vidéo (0 à 1)."""
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    largeur: float = Field(gt=0, le=1)
    hauteur: float = Field(gt=0, le=1)


class ContexteVideoPayload(BaseModel):
    """Contexte de montage associé à une source déjà déposée dans la conversation."""
    video_id: str = Field(min_length=32, max_length=32)
    nom_fichier: Optional[str] = None
    duree_secondes: Optional[float] = Field(default=None, ge=0, le=120)
    debut: Optional[float] = Field(default=None, ge=0)
    fin: Optional[float] = Field(default=None, ge=0)
    zone: Optional[ZoneSelectionVideo] = None
    # Champs renseignés côté serveur uniquement après contrôle de propriété.
    source_path: Optional[str] = None


class EnvoyerMessagePayload(BaseModel):
    # message/agent_id optionnels : sur un appel de reprise (après
    # confirmation_requise), seul `reprise` est fourni -- chat_generateur
    # les ignore dans ce cas (voir core/main.py:chat()).
    message: Optional[str] = None
    agent_id: Optional[str] = None
    historique: List[MessageHistorique] = []
    conversation_id: Optional[str] = None
    # Barre de saisie migrée : sélecteur Courte/Moyenne/Longue, modifiable à chaque message.
    longueur_reponse: Literal["courte", "moyenne", "longue"] = "moyenne"
    # Image jointe au message (URL publique renvoyée par
    # POST /api/uploads/image-chat, voir uploads.py). Quand présente,
    # core/main.py:chat() la fait d'abord décrire/transcrire par Gemini
    # (seul modèle multimodal de la cascade), puis injecte cette
    # description dans le message avant de continuer normalement vers le
    # grand modèle habituel (chantier "image -> grand modele", 11/09/2026)
    # -- voir le commentaire au-dessus de la branche image_url dans chat().
    image_url: Optional[str] = None
    # Correctif 12/09/2026 (Bourama) : plusieurs images jointes au MEME
    # message (ChatIA.tsx envoie ce champ depuis le support multi-fichiers
    # du 17/08, mais il n'existait pas encore ici -- toute image finissait
    # donc silencieusement ignorée par Pydantic et jamais decrite par
    # Gemini). Combinee avec image_url (garde par compatibilite) dans
    # core/main.py:chat().
    image_urls: Optional[List[str]] = None
    # Position GPS transmise explicitement par l'étudiant via un bouton
    # dédié (jamais capturée automatiquement) -- voir core/main.py:chat(),
    # paramètre localisation, injecté en contexte de prompt système.
    localisation: Optional[Localisation] = None
    # Fuseau IANA du navigateur (Intl.DateTimeFormat().resolvedOptions().timeZone),
    # PAS une valeur choisie côté serveur -- voir core/main.py:chat().
    fuseau_horaire: Optional[str] = None
    # Frames JPEG en base64, extraites d'une vidéo uploadée (voir
    # api/uploads.py:uploader_video_chat). Combinable avec image_url mais
    # rarement les deux en même temps en pratique.
    images_base64: Optional[List[str]] = None
    # Atelier vidéo contextuel : la source est vérifiée par utilisateur+conversation
    # avant d'être transmise à core/main.py. Absent = comportement historique.
    contexte_video: Optional[ContexteVideoPayload] = None
    # Zip(s) joint(s) au message (26/09/2026, chantier "zip en
    # conversation") : job_id(s) renvoyé(s) par
    # POST /api/uploads/zip-chat/demarrer, appelé DÈS l'upload (avant
    # l'envoi) -- voir core/zip_chat.py et core/main.py:chat().
    zips_en_attente: Optional[List[str]] = None
    # Icône de recherche web dans la barre de saisie (djiguigne-frontend,
    # 2026-07-23) -- forçage manuel EN PLUS de l'activation automatique
    # déjà possible : le modèle peut de toute façon décider seul
    # d'utiliser Tavily (tool-calling normal, voir INSTRUCTIONS_RECHERCHE_FORCEE
    # dans core/main.py). Ce flag garantit que ça arrive pour CE message
    # précis, quand l'étudiant veut être sûr d'avoir une recherche fraîche.
    recherche_forcee: Optional[bool] = None
    # Bouton "Outils" (2026-07-25, étendu à la MULTI-sélection le 26/07 --
    # voir core/mcp_tools.py:lister_tous_les_outils) : liste des outils
    # sélectionnés manuellement côté frontend (BarreDeSaisie.tsx), zéro,
    # un ou plusieurs à la fois.
    outil_force: Optional[List[str]] = None
    # Bouton "Aucun" à côté des suggestions du routeur (2026-07-31, demande
    # Bourama : le routeur se trompe souvent) -- distinct de outil_force
    # vide/absent : signale explicitement "réponds normalement, ne relance
    # pas le routeur", voir core/main.py:chat() pour le pourquoi (sinon
    # boucle silencieuse de suggestion).
    ignorer_suggestion_outils: Optional[bool] = False
    # Ajouté (2026-07-20) pour exposer le chemin de reprise de chat() --
    # jusqu'ici accessible seulement en appel Python interne (chat.py
    # Streamlit), jamais via cette route HTTP. Voir StatutOutil.tsx /
    # ChatIA.tsx côté djiguigne-frontend pour le flux de confirmation d'outil.
    reprise: Optional[RepriseConfirmation] = None
    # Selecteur de modele premium (02/08/2026, voir core/fournisseurs_llm.py
    # et djiguigne-frontend) : modele_id choisi par l'etudiant/le createur
    # pour CE message (ex: "claude-sonnet-5-5"). None = comportement
    # historique inchange (cascade Groq/Gemini par defaut). REVALIDE ici
    # contre les modeles reellement debloques de l'agent avant d'etre
    # transmis a chat() -- jamais fait confiance a la valeur brute envoyee
    # par le frontend (voir _resoudre_modele_force plus bas).
    modele: Optional[str] = None
    # Reglage "Effort" de la barre de saisie (04/10/2026) : none, low, high ou
    # max. Ne concerne que DeepSeek ; toute autre valeur est ignoree (voir
    # fournisseurs_llm.py:normaliser_effort_reflexion).
    effort_reflexion: Optional[str] = None
    # Bouton "Sans enseignant" (06/08/2026, demande Bourama) -- uniquement
    # pertinent pour les agents à contenu dynamique par matière (Nitrux,
    # voir core/contenu_dynamique_matiere.py) : force le prompt
    # généraliste pour CE message précis, sans utiliser le contenu
    # d'aucun enseignant même si l'étudiant a des matières débloquées.
    # Sans effet sur tous les autres agents (ignoré silencieusement par
    # _construire_system_prompt, qui ne consulte ce flag que pour les
    # agents marqués contenu_dynamique_par_matiere).
    sans_enseignant: Optional[bool] = False
    # Détection appli installée (04/09/2026, demande Bourama) : envoyé par
    # clovis-frontend (ChatFlottant.tsx -> ChatIA.tsx, Capacitor.isNativePlatform()),
    # jamais deviné côté serveur. Sert à forcer explorer_dossier +
    # gerer_dossier_telephone systématiquement quand l'app est installée --
    # voir core/main.py:chat(), outils_forces_contexte.
    natif: Optional[bool] = False
    # Canal en direct (19/09/2026, demande Bourama : "dès que le canal
    # est actif ces outils sont automatiquement envoyés au LLM, c'est le
    # coeur du canal") : envoyé par clovis-frontend tant que le canal en
    # direct est actif (voir lib/contexteCanalEnDirect.tsx), sur CHAQUE
    # message pendant ce temps, pas seulement ceux qui viennent du canal
    # lui-même. Force les outils de la catégorie agent_applicatif (clic)
    # et dire_a_l_etudiant (bulle) dans outils_forces_contexte -- voir
    # core/main.py:chat() -- sans dépendre de ce que le grand modèle
    # pense de demander via demander_outils.
    canal_en_direct: Optional[bool] = False
    # État exact de l'éditeur capturé au moment de l'envoi HTTP. Il est
    # prioritaire sur le cache WebSocket pour le tour courant.
    etat_editeur: Optional[dict] = None
    # Minuteurs du chat (20/09/2026, demande Bourama) : vrai quand ce
    # "message de l'etudiant" n'en est pas un, c'est l'appli qui reveille
    # Clovis parce qu'un minuteur est arrive a zero (voir
    # core/minuteurs.py). Le message est enregistre comme les autres, mais
    # marque meta.automatique pour que le frontend ne l'affiche jamais
    # comme une bulle de l'etudiant, ni maintenant ni au rechargement.
    message_automatique: Optional[bool] = False
    # Versions navigables (20/09/2026, demande Bourama) : voir
    # core/main.py:chat() et core/persistance_echanges.py pour le detail
    # complet des deux cas. `parent_id` = id du dernier message de la
    # branche affichee cote frontend sous lequel attacher ce tour
    # (message.id, voir ChatIA.tsx), None pour le tout premier message.
    # `regenerer` = True uniquement pour "reessayer" : aucune nouvelle
    # ligne "user" n'est creee, `parent_id` designe alors directement le
    # message "user" EXISTANT sous lequel la nouvelle reponse devient une
    # version alternative de l'ancienne (au lieu d'une suite).
    parent_id: Optional[int] = None
    regenerer: Optional[bool] = False
    # Vraie question a ranger dans l'historique quand `message` contient en plus des consignes ou du
    # contexte du client (plugin Thonny, 14/10/2026, demande Bourama : sinon le titre de la
    # conversation et son historique montrent les consignes). Absent : `message` est enregistre.
    message_enregistre: Optional[str] = None
    # Client qui envoie la requete (14/10/2026, demande Bourama). "thonny" : le prompt systeme
    # n'a plus les consignes d'affichage du site mais celles de Thonny (core/prompt_thonny.py).
    # Absent ou inconnu : comportement inchange. `libelles_client` donne le nom des boutons du
    # client dans la langue de l'eleve (cles dans prompt_thonny.LIBELLES_AUTORISES).
    client: Optional[str] = None
    libelles_client: Optional[Dict[str, str]] = None
    # Origine de l'appareil (20/10/2026, demande de Bourama) : annoncée par l'application avec
    # chaque message, jamais devinée par le serveur. Valeurs connues : telephone_appli,
    # telephone_navigateur, pc_navigateur, pc_appli (voir core/origine_appareil.py). Absente ou
    # inconnue : comportement d'avant, rien n'est filtré.
    origine: Optional[str] = None


def _resoudre_modele_force(agent_id, modele_demande):
    """
    Revalide `modele_demande` (envoye par le frontend) contre ce que
    l'agent `agent_id` a REELLEMENT debloque en base (distributeur_debloque/
    palier_debloque, voir api/agents.py et core/fournisseurs_llm.py) --
    jamais de confiance aveugle dans un modele_id venu du client, sinon
    n'importe qui pourrait forcer Claude/GPT sur un agent qui n'a rien
    debloque. Retourne None (repli silencieux sur la cascade Groq
    habituelle) si `modele_demande` est absent, si l'agent est introuvable,
    ou si le modele n'est pas dans la liste autorisee pour CET agent.
    """
    if not modele_demande or not agent_id:
        return None
    try:
        res = (
            supabase.table("agents")
            .select("distributeur_debloque, palier_debloque")
            .eq("id", agent_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (verification modele premium, agent {agent_id}) : {e}")
        return None
    if not res or not res.data:
        return None
    ligne = res.data
    if modele_id_est_autorise(modele_demande, ligne.get("distributeur_debloque"), ligne.get("palier_debloque")):
        return modele_demande
    logging.error(
        f"Modele '{modele_demande}' demande mais non debloque pour l'agent {agent_id} -- ignore, repli sur Groq."
    )
    return None


def _evenements_sse(payload: EnvoyerMessagePayload, user_id: Optional[str]):
    """
    Convertit le générateur Python de chat() en flux SSE (`data: {...}\n\n`
    par événement), le format que `fetch` + `ReadableStream` côté Next.js
    sait consommer nativement sans dépendance supplémentaire.

    Ne change PAS la structure des événements produits par chat() (voir sa
    docstring) -- on les sérialise tels quels, un JSON par ligne `data:`.
    """
    # Canal en direct (19/09/2026) : tant que ce flux tourne, l'etudiant peut
    # envoyer un message qui sera lu par la boucle d'agent au prochain
    # aller-retour (voir core/canal_agent_applicatif.py).
    if user_id:
        definir_lecture_editeur_chat(user_id, payload.conversation_id, payload.etat_editeur)
        debuter_tour(user_id)
    # Jeton d'arrêt de ce tour (12/10/2026, bouton Arrêter) : levé par POST /api/chat/arreter.
    arret = ouvrir_arret(user_id)
    try:
        if payload.reprise is not None:
            generateur = chat_generateur(
                reprise={
                    "etat_reprise": payload.reprise.etat_reprise,
                    "approuve": payload.reprise.approuve,
                },
                arret_tour=arret,
            )
        else:
            generateur = chat_generateur(
                message_utilisateur=payload.message,
                historique=[m.model_dump() for m in payload.historique],
                user_id=user_id,
                agent_id=payload.agent_id,
                conversation_id=payload.conversation_id,
                longueur_reponse=payload.longueur_reponse,
                image_url=payload.image_url,
                image_urls=payload.image_urls,
                localisation=payload.localisation.model_dump() if payload.localisation else None,
                fuseau_horaire=payload.fuseau_horaire,
                images_base64=payload.images_base64,
                zips_en_attente=payload.zips_en_attente,
                recherche_forcee=payload.recherche_forcee,
                outil_force=payload.outil_force,
                ignorer_suggestion_outils=payload.ignorer_suggestion_outils or False,
                modele_force=_resoudre_modele_force(payload.agent_id, payload.modele),
                effort_reflexion=payload.effort_reflexion,
                sans_enseignant=payload.sans_enseignant or False,
                natif=payload.natif or False,
                canal_en_direct=payload.canal_en_direct or False,
                etat_editeur=payload.etat_editeur,
                message_automatique=payload.message_automatique or False,
                parent_id=payload.parent_id,
                regenerer=payload.regenerer or False,
                arret_tour=arret,
                message_enregistre=payload.message_enregistre,
                client=payload.client,
                libelles_client=payload.libelles_client,
                origine=payload.origine,
                contexte_video=payload.contexte_video.model_dump() if payload.contexte_video else None,
            )
        for evenement in generateur:
            yield f"data: {json.dumps(evenement)}\n\n"
    except Exception as e:
        logging.error(f"ERREUR chat() en streaming (agent_id={payload.agent_id}) : {e}")
        yield f"data: {json.dumps({'type': 'reponse', 'texte': 'Une erreur est survenue, réessaie dans un instant.'})}\n\n"
    finally:
        fermer_arret(arret)
        if user_id:
            retirer_lecture_editeur_chat(user_id, payload.conversation_id, payload.etat_editeur)
            retirer_plafond_tour(user_id)
            renvoyer_messages_non_lus(user_id, terminer_tour(user_id))
    # Signal de fin explicite : côté Next.js, permet de savoir que le flux
    # est terminé sans dépendre uniquement de la fermeture de connexion.
    yield "data: [DONE]\n\n"


def _evenement_bloque(texte: str):
    """Même forme d'événement que le message d'erreur générique de
    _evenements_sse ci-dessus -- le frontend l'affiche déjà comme un
    message clair, pas une erreur technique brute (Partie 7)."""
    yield f"data: {json.dumps({'type': 'reponse', 'texte': texte})}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/arreter")
async def arreter_tour(utilisateur=Depends(utilisateur_optionnel)):
    """
    Bouton Arrêter du chat et du canal en direct (12/10/2026, demande Bourama : « arrêter
    c'est arrêter »). Couper la connexion du flux ne suffisait pas : les outils en cours et
    la boucle d'agent continuaient côté serveur. Cette route lève le signal d'arrêt de tous
    les tours en cours du compte (plus de nouvel outil, plus d'attente des outils lancés),
    termine les actions que Clovis attendait de l'appli, et prévient l'appli pour qu'elle
    arrête aussi ce qu'elle avait en file. Sans compte connecté, il n'y a rien à arrêter ici.
    """
    user_id = utilisateur.id if utilisateur else None
    if not user_id:
        return {"tours_arretes": 0, "attentes_annulees": 0}
    tours = demander_arret_utilisateur(user_id)
    attentes = annuler_attentes(user_id)
    await diffuser_arret(user_id)
    return {"tours_arretes": tours, "attentes_annulees": attentes}


@router.post("")
@limiteur.limit("20/minute")
def envoyer_message(request: Request, payload: EnvoyerMessagePayload, utilisateur=Depends(utilisateur_optionnel)):
    """
    Limite : 20 messages/minute par utilisateur connecté (ou par IP pour
    un visiteur anonyme) -- voir core/limitation_debit.py. Empêche le
    spam/abus sur l'endpoint le plus coûteux de l'API (appels Groq/Gemini
    à chaque message).

    Chat accessible aux visiteurs non connectés (utilisateur_optionnel),
    comme sur chat.py -- voir SEUIL_VISITEUR_NON_CONNECTE côté ancien
    frontend Streamlit ; la même limite devra être réimplémentée côté
    Next.js (comptage local, pas de dépendance à cette route pour ça).

    user_id=None si non connecté : chat() gère déjà ce cas (pas de
    mémoire long-terme persistée, pas d'événement "meta" -- voir sa
    docstring), donc rien de spécial à faire ici.

    Partie 7 (06/09, Point 3) : un utilisateur mineur (profiles.est_majeur
    = false explicitement) sans aucun code rattaché a l'accès bloqué --
    vérifié ici, avant même de démarrer le générateur de chat(), pour ne
    jamais consommer un appel LLM pour une réponse qui sera de toute
    façon rejetée.
    """
    user_id = utilisateur.id if utilisateur else None

    # Le montage vidéo est réservé aux comptes connectés et aux sources déposées
    # dans CETTE conversation. Ne jamais accepter le chemin absolu fourni par le client.
    if payload.contexte_video is not None:
        contexte = payload.contexte_video
        if not user_id or not payload.conversation_id:
            raise HTTPException(status_code=401, detail="Connecte-toi pour modifier une vidéo.")
        if (contexte.debut is None) != (contexte.fin is None):
            raise HTTPException(status_code=422, detail="L'intervalle vidéo doit avoir un début et une fin.")
        if contexte.debut is None and contexte.zone is None:
            raise HTTPException(status_code=422, detail="Sélectionne un intervalle ou une zone de l'image.")
        if contexte.zone and (
            contexte.zone.x + contexte.zone.largeur > 1.000001
            or contexte.zone.y + contexte.zone.hauteur > 1.000001
        ):
            raise HTTPException(status_code=422, detail="La zone sélectionnée dépasse les limites de l'image.")
        try:
            metadata = lire_metadonnees_video(user_id, payload.conversation_id, contexte.video_id)
            source = chemin_video(user_id, payload.conversation_id, contexte.video_id)
            duree_reelle = float(metadata.get("duree_secondes") or 0)
        except (ValueError, FileNotFoundError, OSError):
            raise HTTPException(status_code=404, detail="Cette vidéo n'est pas disponible dans cette conversation.") from None
        if contexte.debut is not None and contexte.fin is not None:
            if contexte.fin <= contexte.debut:
                raise HTTPException(status_code=422, detail="La fin doit être après le début de la sélection.")
            if duree_reelle > 0 and contexte.fin > duree_reelle + 0.05:
                raise HTTPException(status_code=422, detail="La sélection dépasse la durée de la vidéo.")
        racine = workspace_dir(user_id, payload.conversation_id, create=False)
        contexte.nom_fichier = metadata.get("nom_fichier") or contexte.nom_fichier
        contexte.duree_secondes = duree_reelle
        contexte.source_path = source.relative_to(racine).as_posix()

    if user_id and acces_chat_bloque_pour_mineur(user_id):
        return StreamingResponse(
            _evenement_bloque(
                "L'accès au chat est réservé aux comptes mineurs ayant reçu un code de leur professeur ou établissement. Entre un code dans \"Mon espace\" pour continuer."
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return StreamingResponse(
        _evenements_sse(payload, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # évite le buffering côté proxy (Railway/nginx)
        },
    )
