"""
Ajoute le 15/09/2026 (demande Bourama) : jusqu'ici, l'historique renvoye
par le frontend a chaque nouveau message ne contenait que le texte final
(role/content). Tout resultat d'outil obtenu a un tour precedent (lecture
de bibliotheque, skill, recherche web, code recu...) etait donc invisible
pour le modele au tour suivant, qui devait rappeler l'outil pour le
"redecouvrir". Ce module reinjecte ces resultats dans ce qui part au
modele (voir core/main.py, construction de messages_base).

Format choisi : le resultat de chaque outil est prefixe DANS le contenu du
message assistant concerne (pas un message separe). Cela garde une stricte
alternance user/assistant, identique a la structure d'origine de
l'historique, donc aucune adaptation par fournisseur necessaire (Groq,
DeepSeek, Gemini, premium), contrairement au format natif tool_calls/
tool_call_id : un outil deja execute a un tour PASSE n'est plus un appel en
attente de reponse protocolaire, juste un fait de contexte.

Budget : voir SEUIL_CARACTERES_OUTILS_HISTORIQUE (constantes_agent.py).

Chantier du 27/09/2026 (demande explicite Bourama, reduire les couts sans
perdre de contexte) : au-dela du seuil, les resultats les plus ANCIENS ne
sont plus renvoyes. Ils etaient auparavant condenses par un appel
supplementaire a un petit modele, ce qui coutait a chaque franchissement
du seuil. Ils sont maintenant remplaces par un simple rappel (voir
_pointeur_outil), gratuit et deterministe. Rien n'est perdu : le contenu
complet reste recuperable via l'outil rappeler_resultat_outil (voir
core/outils_rappel_resultats.py) si le modele en a reellement besoin. Les
resultats RECENTS restent intacts.
"""

from constantes_agent import SEUIL_CARACTERES_OUTILS_HISTORIQUE

# Un rappel ne remplace un resultat que si le resultat est nettement plus
# long que le rappel lui-meme, sinon on ferait grossir le contexte au lieu
# de le reduire.
_MARGE_MIN_REMPLACEMENT = 100


def _bloc_outil(o):
    """Un seul resultat d'outil (voir api/chat.py:OutilHistorique), mis en
    forme pour le modele."""
    nom = o.get("nomLisible") or o.get("nomOutil") or "Outil"
    resultat = o.get("resultat") or ""
    return f"[Résultat de l'outil déjà exécuté -- {nom}]\n{resultat}"


def _pointeur_outil(o, mentionner_outil_rappel=True):
    """Remplace un resultat d'outil devenu trop ancien par un simple rappel
    de son existence, sans son contenu. Gratuit (aucun appel modele).
    `mentionner_outil_rappel` vaut False quand on sait DEJA que
    rappeler_resultat_outil n'est pas propose ce tour-ci (voir core/main.py).
    Meme quand il vaut True, la formulation reste souple (28/09/2026) : un
    chemin de reponse sans aucun outil peut survenir apres coup (filet de
    secours Gemini, voir core/main.py) sans que ce calcul ait pu le savoir a
    l'avance -- le modele doit pouvoir continuer sans ce detail si besoin."""
    nom = o.get("nomLisible") or o.get("nomOutil") or "Outil"
    if mentionner_outil_rappel:
        return (
            f"[Outil déjà exécuté plus tôt dans cette conversation : {nom}. "
            f"Résultat non affiché ici pour ne pas surcharger le contexte. "
            f"Si l'outil rappeler_resultat_outil est disponible et que ce "
            f"résultat redevient utile, utilise-le plutôt que de réexécuter "
            f"cet outil. Sinon, continue normalement sans ce détail.]"
        )
    return (
        f"[Outil déjà exécuté plus tôt dans cette conversation : {nom}. "
        f"Résultat non affiché ici pour ne pas surcharger le contexte.]"
    )


def _blocs_outils(historique):
    """[(index_message, outil_brut, texte_du_bloc)] dans l'ordre chronologique."""
    blocs = []
    for i, m in enumerate(historique or []):
        if m.get("role") != "assistant":
            continue
        for o in (m.get("outils") or []):
            blocs.append((i, o, _bloc_outil(o)))
    return blocs


def a_des_outils_allegers(historique):
    """Vrai si le volume total de resultats d'outils depasse le seuil, donc
    si enrichir_historique_avec_outils va remplacer les plus anciens par un
    rappel. Utilise par core/main.py pour proposer rappeler_resultat_outil
    au modele seulement quand il peut en avoir besoin."""
    return sum(len(t) for _, _, t in _blocs_outils(historique)) > SEUIL_CARACTERES_OUTILS_HISTORIQUE


def enrichir_historique_avec_outils(historique, mentionner_outil_rappel=True):
    """
    `historique` : liste de dicts {role, content, outils?} tels qu'envoyes
    par le frontend (voir api/chat.py:MessageHistorique). `outils` provient
    de meta.outils, deja sauvegarde pour l'affichage (voir
    core/persistance_echanges.py). Renvoie une NOUVELLE liste (n'altere
    jamais l'original), meme longueur, memes roles. Seul le `content` des
    messages assistant concernes est enrichi.

    Renvoie l'historique tel quel si aucun message n'a d'outils.
    """
    blocs = _blocs_outils(historique)

    if not blocs:
        return historique

    taille_totale = sum(len(t) for _, _, t in blocs)

    if taille_totale > SEUIL_CARACTERES_OUTILS_HISTORIQUE:
        # Garde les plus RECENTS intacts (en partant de la fin), remplace le
        # reste (les plus ANCIENS) par un simple rappel de leur existence,
        # un par outil concerne : rappeler_resultat_outil cherche par
        # description, un rappel par outil (avec son nom) lui donne une
        # meilleure chance de retrouver le bon.
        taille_cumulee_recente = 0
        coupure = len(blocs)
        for k in range(len(blocs) - 1, -1, -1):
            taille_cumulee_recente += len(blocs[k][2])
            if taille_cumulee_recente > SEUIL_CARACTERES_OUTILS_HISTORIQUE:
                coupure = k + 1
                break
        anciens, recents = blocs[:coupure], blocs[coupure:]
        allege = []
        for idx, o, texte in anciens:
            rappel = _pointeur_outil(o, mentionner_outil_rappel)
            if len(texte) > len(rappel) + _MARGE_MIN_REMPLACEMENT:
                allege.append((idx, o, rappel))
            else:
                allege.append((idx, o, texte))
        blocs = allege + recents

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
