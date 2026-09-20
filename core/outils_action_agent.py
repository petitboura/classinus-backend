"""
Chantier agent applicatif (voir plan-agent-applicatif-clovis.md),
chantier C.

Outil expose UNIQUEMENT cote chat eleve (@mcp_generation.tool(), jamais
core/registre_outils_public.py ou equivalent serveur MCP public) --
meme logique que core/outils_verification_code_actif.py.

Renomme de "executer_action_appareil" (nom provisoire propose avant la
decision Bourama) en "executer_action_application" : il n'y a plus de
notion d'appareil cible, voir core/canal_agent_applicatif.py.
"""

import asyncio

from core.canal_agent_applicatif import (
    pousser_texte_clovis as _pousser_texte_clovis,
    demander_ouverture_canal as _demander_ouverture_canal,
    demander_execution_action as _demander_execution_action,
    demander_clic_generique as _demander_clic_generique,
    demander_pointage_action as _demander_pointage_action,
    demander_ecriture_champ as _demander_ecriture_champ,
    observer_changement_ecran as _observer_changement_ecran,
    photographier_ecran as _photographier_ecran,
)
from core.outils_generation_commun import mcp_generation, Context


@mcp_generation.tool()
async def executer_action_application(action_id: str, ctx: Context) -> str:
    """
    Declenche un clic dans l'application Classinus a la place de
    l'etudiant, sur l'element `action_id`.

    Revise le 19/09/2026 (decision Bourama, chantier "agent applicatif
    continu") : plus d'outil separe a appeler avant celui-ci pour
    obtenir la liste -- les elements cliquables actuellement a l'ecran
    (id, description) sont deja fournis directement dans ce prompt
    systeme, tenus a jour automatiquement a chaque message (mecanisme de
    poussee d'etat, chantier D). Des que l'etudiant a besoin que tu
    cliques sur quelque chose, utilise cet outil DIRECTEMENT avec l'id
    correspondant -- ne jamais deviner ni inventer un identifiant, et ne
    jamais reutiliser un id qui n'apparait plus dans la liste la plus
    recente qui t'a ete fournie.

    Ne force JAMAIS un clic sur un element que tu ne vois pas dans cette
    liste. Si ce que tu cherches n'y est pas, cherche les boutons qui
    ouvrent quelque chose (menu, "plus", tiroir, panneau, onglet...),
    clique dessus, puis lis le resultat : apres chaque clic reussi, ce
    resultat decrit les elements apparus (avec leur id) et disparus. Si
    rien ne correspond apres avoir essaye les ouvreurs plausibles, dis-le
    a l'etudiant au lieu de deviner.

    Plus aucune confirmation cote etudiant par defaut : l'execution est
    immediate des l'appel de cet outil, sans etape intermediaire. N'agis
    que quand l'etudiant a reellement demande cette action (ou l'a
    clairement acceptee dans la conversation), jamais de facon spontanee.
    Tu peux quand meme demander confirmation dans ta reponse normale du
    chat avant d'appeler cet outil si l'etudiant te l'a explicitement
    demande, ou si tu juges toi-meme plus prudent de confirmer d'abord.

    NECESSITE que l'application soit ouverte quelque part pour ce
    compte (peu importe l'onglet ou l'appareil, voir
    core/canal_agent_applicatif.py) -- sinon echoue immediatement avec un
    message clair a relayer a l'etudiant.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    if not action_id:
        return "Erreur : paramètre 'action_id' manquant."

    avant = _photographier_ecran(user_id)
    resultat = await _demander_execution_action(user_id, action_id)

    if resultat is None:
        return (
            "Aucune réponse de l'application : soit elle n'est ouverte nulle part pour ce compte, "
            "soit l'action n'est plus disponible à l'écran nulle part où elle est ouverte."
        )
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    return "Action exécutée avec succès.\n" + await _observer_changement_ecran(user_id, avant)


@mcp_generation.tool()
async def executer_clic_generique(selecteur: str, description: str, ctx: Context) -> str:
    """
    Chantier F, revise le 17/09/2026 (scan generique) puis le 19/09/2026
    (chantier "agent applicatif continu", retrait de l'outil
    lister_actions_disponibles). Filet de securite EXCEPTIONNEL : ne
    JAMAIS s'en servir pour deviner un element qui n'apparait pas dans la
    liste fournie dans ce prompt systeme (cliquer au hasard sur un
    selecteur invente est interdit). A n'utiliser que si un selecteur
    exact t'a ete donne explicitement (par l'etudiant, ou par un resultat
    d'outil). Sinon, explore l'application avec executer_action_application
    en ouvrant les menus, tiroirs et onglets visibles dans la liste. Ne
    jamais l'utiliser en doublon d'un élément déjà présent dans la liste.

    `selecteur` est un sélecteur CSS visant un unique élément cliquable
    (bouton, lien...) actuellement affiché. `description` est une
    phrase courte et claire décrivant l'action, affichée à l'étudiant
    dans la bulle de dialogue du canal en direct pendant l'exécution.

    Revise le 19/09/2026 (decision Bourama) : plus aucune confirmation
    cote etudiant, l'execution est immediate des l'appel de cet outil.

    Si l'élément n'est pas trouvé, ou trouvé mais désactivé/invisible,
    l'application le traite comme indisponible plutôt que de risquer un
    clic sur autre chose -- relayer clairement à l'étudiant que l'action
    demandée n'a pas pu être localisée à l'écran.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    if not selecteur:
        return "Erreur : paramètre 'selecteur' manquant."
    if not description:
        return "Erreur : paramètre 'description' manquant."

    avant = _photographier_ecran(user_id)
    resultat = await _demander_clic_generique(user_id, selecteur, description)

    if resultat is None:
        return (
            "Aucune réponse de l'application : soit elle n'est ouverte nulle part pour ce compte, "
            "soit l'élément visé n'a été trouvé (visible et actif) nulle part où elle est ouverte."
        )
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    return "Action exécutée avec succès.\n" + await _observer_changement_ecran(user_id, avant)


@mcp_generation.tool()
async def montrer_element_application(action_id: str, ctx: Context) -> str:
    """
    Chantier G : mode guidage / visite guidée. Déplace UNIQUEMENT le
    curseur virtuel vers l'élément `action_id` (identifiant fourni
    automatiquement dans ce prompt systeme, detecte par le scan
    générique), SANS jamais l'exécuter -- pour montrer une nouveauté ou
    un endroit précis de l'application à l'étudiant.
    Décrire ce que fait cet élément dans le message envoyé à l'étudiant
    au même moment, cet outil ne fait qu'un pointage visuel silencieux.

    Pour une visite en plusieurs étapes, appeler cet outil une fois par
    étape, en laissant l'étudiant lire l'explication entre deux (pause
    à chaque étape, décision Bourama) -- ne jamais enchaîner plusieurs
    pointages sans texte explicatif entre eux.

    Si l'étudiant doit ensuite cliquer lui même, ne pas appeler
    executer_action_application à sa place : laisser l'étudiant agir.
    Si Classinus doit agir à sa place, utiliser executer_action_application
    séparément après (ou à la place de) ce pointage.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    if not action_id:
        return "Erreur : paramètre 'action_id' manquant."

    resultat = await _demander_pointage_action(user_id, action_id)

    if resultat is None:
        return (
            "Aucune réponse de l'application : soit elle n'est ouverte nulle part pour ce compte, "
            "soit cette action n'est plus disponible à l'écran nulle part où elle est ouverte."
        )
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    return "Curseur déplacé vers l'élément avec succès."


@mcp_generation.tool()
async def ecrire_dans_champ(action_id: str, texte: str, ctx: Context) -> str:
    """
    Ajoute le 20/09/2026 (demande Bourama) : écrit `texte` dans le champ
    de saisie `action_id` à la place de l'étudiant, avec une frappe
    visible (l'étudiant voit le texte apparaître progressivement,
    lettre par lettre, comme s'il était tapé). `action_id` doit être un
    identifiant de champ de saisie (input ou textarea) présent dans la
    liste des éléments à l'écran fournie dans ce prompt système, jamais
    deviné ni inventé. Pour un menu déroulant, une case à cocher, ou
    tout autre élément qui ne se remplit pas par frappe, utilise
    executer_action_application à la place.

    Remplace entièrement le contenu actuel du champ, ne l'ajoute pas à
    la suite de ce qui y est déjà écrit.

    Plus aucune confirmation côté étudiant par défaut, même principe
    que executer_action_application : l'exécution est immédiate dès
    l'appel de cet outil. N'agis que quand l'étudiant a réellement
    demandé cette saisie (ou l'a clairement acceptée dans la
    conversation), jamais de façon spontanée.

    NECESSITE que l'application soit ouverte quelque part pour ce
    compte, même règle que les autres outils de ce fichier.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    if not action_id:
        return "Erreur : paramètre 'action_id' manquant."
    if not texte:
        return "Erreur : paramètre 'texte' manquant."

    avant = _photographier_ecran(user_id)
    resultat = await _demander_ecriture_champ(user_id, action_id, texte)

    if resultat is None:
        return (
            "Aucune réponse de l'application : soit elle n'est ouverte nulle part pour ce compte, "
            "soit ce champ n'est plus disponible à l'écran nulle part où elle est ouverte."
        )
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    return "Texte écrit avec succès.\n" + await _observer_changement_ecran(user_id, avant)


# Plafond de longueur d'un commentaire en direct : la bulle du canal est
# faite pour une ou deux phrases lues en passant, pas pour un paragraphe.
LONGUEUR_MAX_TEXTE_DIRECT = 400

# Duree d'affichage de la bulle voulue par le modele (20/09/2026, demande
# Bourama : la bulle disparaissait trop tot, et le modele est le mieux placé
# pour savoir combien de temps se lit son message). Bornes larges, pas des
# limites produit tranchees avec Bourama (a valider), regroupees ici pour
# etre faciles a changer.
DUREE_MIN_BULLE_SECONDES = 3
DUREE_MAX_BULLE_SECONDES = 60

# Quand le modele demande d'attendre que l'etudiant ait fini de lire avant
# de continuer (attendre_lecture), attente maximale : au dela, une action
# bloquee trop longtemps ressemble a une panne.
ATTENTE_MAX_LECTURE_SECONDES = 30


def _duree_automatique_secondes(texte: str) -> float:
    """Meme formule que la duree automatique du frontend
    (lib/contexteCanalEnDirect.tsx : 5 s minimum, 60 ms par caractere,
    15 s maximum), utilisee ici seulement pour savoir combien de temps
    attendre quand le modele n'a pas donne de duree. A garder identique
    des deux cotes."""
    return min(15.0, max(5.0, len(texte) * 0.06))


@mcp_generation.tool()
async def dire_a_l_etudiant(
    texte: str,
    ctx: Context,
    duree_secondes: int = 0,
    attendre_lecture: bool = False,
) -> str:
    """
    Chantier P (canal en direct, decision Bourama du 19/09/2026) :
    affiche un court commentaire dans une bulle qui suit la souris de
    l'etudiant, PENDANT que tu agis dans l'application. C'est toi qui vois
    l'ecran et qui sais ce que tu fais : utilise cet outil pour dire, au
    bon moment, ce qu'un guide humain dirait a voix haute a cote de
    quelqu'un (ce que tu vois, ce que tu vas faire, pourquoi, ce qui
    bloque).

    L'etudiant ne voit QUE cette bulle, une a la fois : chaque nouveau
    message remplace le precedent, et il ne voit ni tes reflexions, ni les
    resultats de tes outils, ni le reste de ta reponse. Chaque message doit
    donc se comprendre seul.

    A appeler entre deux actions, avant ou apres un executer_action_application
    ou un montrer_element_application, seulement quand ca apporte
    quelque chose a l'etudiant. Une ou deux phrases courtes, dans la langue
    de l'etudiant, en texte brut (pas de mise en forme). Ne pas repeter la
    description de l'action en cours (l'application l'affiche deja), ne pas
    commenter chaque clic, ne pas s'en servir pour la reponse finale : celle-ci
    reste dans ta reponse normale du chat.

    `duree_secondes` : combien de temps la bulle reste affichee (3 a 60),
    a regler d'apres la longueur de ton message, environ 1 seconde pour 15
    caracteres avec 4 secondes minimum, plus si tu poses une question. Tant
    qu'elle est affichee, le nom des actions que tu fais ne la remplace pas.
    Sans valeur (0), la duree est automatique.

    `attendre_lecture` : mets vrai quand la lecture est INDISPENSABLE avant
    ta prochaine action, par exemple quand tu presentes ou expliques ce
    que tu vas faire ou ce qu'il va voir : tu ne rends alors la main
    qu'une fois le delai ecoule (30 secondes maximum). Laisse faux quand
    tu informes seulement en passant : tu enchaines aussitot et la bulle
    reste affichee pendant ce temps.

    Le texte est aussi garde dans le resultat de l'appel, donc visible
    dans l'historique de la conversation meme si l'etudiant n'a pas vu la
    bulle. Si l'application n'est ouverte nulle part pour ce compte, la
    bulle ne peut pas s'afficher : le dire alors dans ta reponse normale.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    propre = (texte or "").strip()
    if not propre:
        return "Erreur : paramètre 'texte' manquant."
    if len(propre) > LONGUEUR_MAX_TEXTE_DIRECT:
        return (
            f"Erreur : texte trop long ({len(propre)} caractères, maximum {LONGUEUR_MAX_TEXTE_DIRECT}). "
            "Reformule en une ou deux phrases courtes."
        )

    # Durée voulue par le modèle, ramenée dans les bornes plutôt que refusée :
    # un 90 ou un 1 ne doit pas faire perdre le message.
    duree_voulue = 0
    if isinstance(duree_secondes, int) and not isinstance(duree_secondes, bool) and duree_secondes > 0:
        duree_voulue = max(DUREE_MIN_BULLE_SECONDES, min(DUREE_MAX_BULLE_SECONDES, duree_secondes))

    atteintes = await _pousser_texte_clovis(user_id, propre, duree_voulue or None)

    if atteintes == 0:
        return (
            "Aucun affichage : l'application n'est ouverte nulle part pour ce compte, "
            "l'étudiant n'a rien vu. Dis-le dans ta réponse normale à la place."
        )

    duree_effective = float(duree_voulue) if duree_voulue else _duree_automatique_secondes(propre)
    resultat = (
        f"Message affiché à l'étudiant pendant environ {duree_effective:.0f} secondes, "
        f"il remplace la bulle précédente : {propre}"
    )
    if attendre_lecture:
        attente = min(duree_effective, float(ATTENTE_MAX_LECTURE_SECONDES))
        await asyncio.sleep(attente)
        resultat += f"\nAttendu {attente:.0f} secondes pour qu'il ait le temps de lire."
    return resultat


# Texte envoye comme message du chat, a la fin du tour, une fois le canal
# ouvert (voir core/canal_agent_applicatif.py:demander_ouverture_canal).
TEXTE_SUITE_DEMO_CANAL = "Montre-moi maintenant le canal en direct, avec quelques exemples."


@mcp_generation.tool()
async def ouvrir_canal_en_direct(ctx: Context) -> str:
    """
    Demo uniquement (decision Bourama du 20/09/2026) : ouvre le canal en
    direct (curseur qui bouge et clique, bulle de dialogue) pour pouvoir
    le DEMONTRER. La demo tourne dans le chat normal, ou tu n'as pas les
    outils de clic : cet outil est le seul moyen de les obtenir.

    A appeler UNIQUEMENT en mode demo, quand l'utilisateur choisit de voir
    le canal en direct, ou quand tu as fini les affichages et les outils
    et qu'il ne l'a toujours pas choisi. Ne l'appelle pas si tu as deja
    les outils de clic, ni une deuxieme fois dans la meme conversation.

    Apres l'appel, termine ta reponse par UNE phrase courte annoncant que
    le canal s'ouvre : la suite de la demo demarre toute seule dans un
    nouveau tour, avec les outils de clic disponibles.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."
    conversation_id = ctx.request_context.request.query_params.get("conversation_id") or None

    atteintes = await _demander_ouverture_canal(user_id, conversation_id, TEXTE_SUITE_DEMO_CANAL)
    if atteintes == 0:
        return (
            "Impossible d'ouvrir le canal : l'application n'est ouverte nulle part pour ce compte. "
            "Dis-le simplement a l'utilisateur et termine la demo sans cette partie."
        )
    return (
        "Le canal en direct s'ouvre. Termine ta reponse par une seule phrase courte qui l'annonce "
        "(sans bloc question) : la suite de la demo demarre automatiquement."
    )
