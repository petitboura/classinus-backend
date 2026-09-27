"""
Ajoute le 27/09/2026 (demande explicite Bourama, "reduire les couts sans
jamais perdre de contexte") -- meme principe que core/historique_outils.py,
applique cette fois au texte brut des MESSAGES eux-memes (questions de
l'utilisateur, reponses de l'IA), pas seulement aux resultats d'outils.

Avant ce module : `historique` (voir api/chat.py:MessageHistorique) etait
renvoye INTEGRALEMENT au modele a chaque nouveau message, sans jamais
retirer ni alleger quoi que ce soit -- une conversation de 200 messages
repayait donc l'integralite des 199 precedents a chaque tour suivant, pour
toujours.

Nouveau principe : au-dela de SEUIL_CARACTERES_HISTORIQUE_CONVERSATION
(constantes_agent.py), les messages les plus ANCIENS ne sont plus envoyes
en entier -- ils sont remplaces par un simple rappel (role + apercu du
debut, genere sans aucun appel modele, donc gratuit) : le contenu complet
reste recuperable via l'outil rappeler_echange_conversation (voir
core/outils_rappel_resultats.py) si le modele en a reellement besoin. Les
echanges RECENTS restent intacts, mot pour mot, inchange.

Applique AVANT enrichir_historique_avec_outils (core/main.py) : les deux
fonctions sont independantes, chacune allege sa propre partie (celle-ci le
texte des messages, l'autre les resultats d'outils qui y sont rattaches).
"""

from constantes_agent import SEUIL_CARACTERES_HISTORIQUE_CONVERSATION

# Longueur de l'apercu garde dans le rappel -- juste assez pour que le
# modele reconnaisse le sujet et sache s'il vaut la peine d'aller
# rechercher l'echange complet.
_LONGUEUR_APERCU = 80

_LIBELLE_ROLE = {"user": "question de l'utilisateur", "assistant": "réponse de l'IA"}


def _apercu(texte):
    texte = (texte or "").strip().replace("\n", " ")
    if len(texte) <= _LONGUEUR_APERCU:
        return texte
    return texte[:_LONGUEUR_APERCU].rstrip() + "…"


def _pointeur_message(role, contenu):
    libelle = _LIBELLE_ROLE.get(role, role)
    return (
        f"[Message plus tôt dans cette conversation -- {libelle}, sujet : "
        f"\"{_apercu(contenu)}\". Texte complet non affiché ici pour ne pas "
        f"surcharger le contexte -- utilise rappeler_echange_conversation "
        f"si tu as besoin de le relire en entier.]"
    )


def alleger_historique_ancien(historique):
    """
    `historique` : liste de dicts {role, content, outils?} tels qu'envoyes
    par le frontend (voir api/chat.py:MessageHistorique). Renvoie une
    NOUVELLE liste (n'altere jamais l'original), meme longueur, memes
    roles et memes `outils` -- seul le `content` des messages les plus
    anciens est remplace par un rappel si le volume total le justifie.

    Ignore silencieusement (renvoie l'historique tel quel) si le volume
    total reste sous le seuil -- aucun changement de comportement pour
    une conversation courte ou moyenne.
    """
    taille_totale = sum(len(m.get("content") or "") for m in historique)
    if taille_totale <= SEUIL_CARACTERES_HISTORIQUE_CONVERSATION:
        return historique

    # Garde les messages les plus RECENTS intacts (en partant de la fin),
    # allege le reste (les plus ANCIENS) -- meme technique que
    # core/historique_outils.py:enrichir_historique_avec_outils.
    taille_cumulee_recente = 0
    coupure = len(historique)
    for k in range(len(historique) - 1, -1, -1):
        taille_cumulee_recente += len(historique[k].get("content") or "")
        if taille_cumulee_recente > SEUIL_CARACTERES_HISTORIQUE_CONVERSATION:
            coupure = k + 1
            break

    resultat = []
    for i, m in enumerate(historique):
        if i < coupure:
            resultat.append({**m, "content": _pointeur_message(m.get("role"), m.get("content"))})
        else:
            resultat.append(m)
    return resultat
