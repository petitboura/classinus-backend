"""
Ajoute le 15/09/2026 (demande Bourama) : jusqu'ici, l'historique renvoye
par le frontend a chaque nouveau message ne contenait que le texte final
(role/content) -- tout resultat d'outil obtenu a un tour precedent
(lecture de bibliotheque, skill, recherche web, code recu...) etait donc
invisible pour le modele au tour suivant, qui devait rappeler l'outil pour
le "redecouvrir". Ce module reinjecte ces resultats dans ce qui part au
modele (voir core/main.py, construction de messages_base).

Format choisi : le resultat de chaque outil est prefixe DANS le contenu du
message assistant concerne (pas un message separe) -- garde une stricte
alternance user/assistant, identique a la structure d'origine de
l'historique, donc aucune adaptation par fournisseur necessaire (Groq,
DeepSeek, Gemini, premium) contrairement au format natif tool_calls/
tool_call_id (propre a Groq/OpenAI) : un outil deja execute a un tour
PASSE n'est plus un appel en attente de reponse protocolaire, juste un
fait de contexte.

Budget : voir SEUIL_CARACTERES_OUTILS_HISTORIQUE (constantes_agent.py).

CHANTIER 27/09/2026 (demande explicite Bourama, "reduire les couts sans
perdre de contexte") : au-dela du seuil, les resultats les plus ANCIENS
n'etaient jusqu'ici pas retires, seulement condenses via un appel
supplementaire a MODELE_RESUME (_resumer_outils_anciens, retire) -- un
cout a chaque fois que le seuil etait franchi, meme quand ce vieux
resultat ne servait plus jamais a rien. Remplace par un simple RAPPEL
("[Outil deja execute plus tot -- <nom>]", voir _pointeur_outil), gratuit
et deterministe (aucun appel modele), rien n'est perdu : le contenu
complet reste recuperable via l'outil rappeler_resultat_outil (voir
core/outils_rappel_resultats.py) si le modele en a reellement besoin.
Les resultats RECENTS restent intacts, inchange.
"""

from constantes_agent import SEUIL_CARACTERES_OUTILS_HISTORIQUE


def _bloc_outil(o):
    """Un seul resultat d'outil (voir api/chat.py:OutilHistorique), mis en
    forme pour le modele."""
    nom = o.get("nomLisible") or o.get("nomOutil") or "Outil"
    resultat = o.get("resultat") or ""
    return f"[Résultat de l'outil déjà exécuté -- {nom}]\n{resultat}"


def _pointeur_outil(o):
    """Remplace un resultat d'outil devenu trop ancien par un simple
    rappel de son existence, sans son contenu -- voir
    core/outils_rappel_resultats.py:rappeler_resultat_outil pour aller le
    rechercher si besoin. Gratuit (aucun appel modele), contrairement a
    l'ancien resume via MODELE_RESUME."""
    nom = o.get("nomLisible") or o.get("nomOutil") or "Outil"
    return (
        f"[Outil déjà exécuté plus tôt dans cette conversation -- {nom}. "
        f"Résultat non affiché ici pour ne pas surcharger le contexte -- "
        f"utilise rappeler_resultat_outil si tu en as besoin, plutôt que "
        f"de réexécuter cet outil.]"
    )


def enrichir_historique_avec_outils(historique):
    """
    `historique` : liste de dicts {role, content, outils?} tels qu'envoyes
    par le frontend (voir api/chat.py:MessageHistorique -- `outils`
    provient de meta.outils, deja sauvegarde pour l'affichage, voir
    core/persistance_echanges.py). Renvoie une NOUVELLE liste (n'altere
    jamais l'original), meme longueur, memes roles -- seul le `content`
    des messages assistant concernes est enrichi.

    Ignore silencieusement (renvoie l'historique tel quel) si aucun
    message n'a d'outils, ou si le resume de secours echoue ET que la
    troncature de secours suffit -- ce module ne doit jamais faire
    planter un message pour cette seule raison.
    """
    # [(index_message, outil_brut, texte_du_bloc)], ordre chronologique --
    # l'outil brut est garde a cote du texte pour pouvoir construire un
    # simple rappel (nom seulement) si ce bloc s'avere trop ancien.
    blocs = []
    for i, m in enumerate(historique):
        if m.get("role") != "assistant":
            continue
        for o in (m.get("outils") or []):
            blocs.append((i, o, _bloc_outil(o)))

    if not blocs:
        return historique

    taille_totale = sum(len(t) for _, _, t in blocs)

    if taille_totale > SEUIL_CARACTERES_OUTILS_HISTORIQUE:
        # Garde les plus RECENTS intacts (en partant de la fin), remplace
        # le reste (les plus ANCIENS) par un simple rappel de leur
        # existence -- un par outil concerne, pas un resume groupe :
        # rappeler_resultat_outil cherche par description, un rappel par
        # outil (avec son nom) lui donne une meilleure chance de
        # retrouver le bon.
        taille_cumulee_recente = 0
        coupure = len(blocs)
        for k in range(len(blocs) - 1, -1, -1):
            taille_cumulee_recente += len(blocs[k][2])
            if taille_cumulee_recente > SEUIL_CARACTERES_OUTILS_HISTORIQUE:
                coupure = k + 1
                break
        anciens, recents = blocs[:coupure], blocs[coupure:]
        blocs = [(idx, o, _pointeur_outil(o)) for idx, o, _ in anciens] + recents

    par_index = {}
    for idx, _o, texte in blocs:
        par_index.setdefault(idx, []).append(texte)

    resultat = []
    for i, m in enumerate(historique):
        if i in par_index:
            contexte = "\n\n".join(par_index[i])
            contenu = f"{contexte}\n\n[Réponse donnée à ce moment-là]\n{m['content']}"
            resultat.append({"role": m["role"], "content": contenu})
        else:
            resultat.append({"role": m["role"], "content": m["content"]})
    return resultat
