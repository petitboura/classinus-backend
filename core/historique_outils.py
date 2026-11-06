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

Changement du 06/11/2026 (demande Bourama) : les resultats d'outils ne sont plus
ecrits dans le contenu des messages assistant. Ce format, repete a chaque tour, etait
imite par certains modeles (GLM notamment) qui recopiaient les blocs dans leur reponse
visible. Les messages assistant redeviennent du texte seul (historique_texte_seul), ce
qui garde l'alternance user/assistant, et les resultats sont rassembles dans un journal
(journal_outils_historique) ajoute au message systeme. Meme budget, meme allegement,
memes pointeurs de rappel : seul l'endroit et la presentation changent.
"""

import json

from constantes_agent import SEUIL_CARACTERES_OUTILS_HISTORIQUE
from core.plafonds_reglables import PLAFOND_ARGUMENTS_OUTIL_HISTORIQUE, PLAFOND_RESULTAT_OUTIL_HISTORIQUE

# Un rappel ne remplace un resultat que si le resultat est nettement plus
# long que le rappel lui-meme, sinon on ferait grossir le contexte au lieu
# de le reduire.
_MARGE_MIN_REMPLACEMENT = 100


def _bloc_outil(o):
    """Un seul resultat d'outil (voir api/chat.py:OutilHistorique), mis en
    forme pour le modele."""
    nom = o.get("nomLisible") or o.get("nomOutil") or "Outil"
    # Le resultat complet (resultatComplet) existe quand celui d'affichage a ete coupe pour
    # l'ecran : le modele doit revoir le premier, jamais la version coupee.
    resultat = o.get("resultatComplet") or o.get("resultat") or ""
    arguments = (o.get("arguments") or "").strip()
    lignes = [f"Outil : {nom}"]
    if arguments:
        lignes.append(f"Appel : {arguments}")
    lignes.append(f"Résultat :\n{resultat}")
    return "\n".join(lignes)


def _couper(texte, plafond):
    if len(texte) <= plafond:
        return texte
    return texte[:plafond] + f"\n... (coupé, {len(texte)} caractères au total)"


def champs_historique_outil(arguments, resultat_brut, resultat_affiche):
    """
    Champs a ajouter a l'evenement outil_resultat (et a meta.outils) pour que le modele
    retrouve, aux tours suivants, ce que l'outil a fait.

    `arguments` : arguments de l'appel, en texte JSON ou en dict (None ou vide : rien n'est
    ajoute). `resultat_brut` : resultat complet de l'outil. `resultat_affiche` : version
    deja coupee pour l'ecran. `resultat_complet` n'est ajoute que si la version d'affichage
    a ete coupee, pour ne jamais envoyer le meme texte deux fois.
    """
    champs = {}
    if isinstance(arguments, dict):
        texte_arguments = json.dumps(arguments, ensure_ascii=False, default=str) if arguments else ""
    else:
        texte_arguments = (arguments or "").strip()
    if texte_arguments and texte_arguments not in ("{}", "null"):
        champs["arguments"] = _couper(texte_arguments, PLAFOND_ARGUMENTS_OUTIL_HISTORIQUE)
    if not isinstance(resultat_brut, str):
        resultat_brut = str(resultat_brut)
    if resultat_brut != resultat_affiche:
        champs["resultat_complet"] = _couper(resultat_brut, PLAFOND_RESULTAT_OUTIL_HISTORIQUE)
    return champs


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
            f"Outil déjà exécuté plus tôt dans cette conversation : {nom}. "
            f"Résultat non affiché ici pour ne pas surcharger le contexte. "
            f"Si l'outil rappeler_resultat_outil est disponible et que ce "
            f"résultat redevient utile, utilise-le plutôt que de réexécuter "
            f"cet outil. Sinon, continue normalement sans ce détail."
        )
    return (
        f"Outil déjà exécuté plus tôt dans cette conversation : {nom}. "
        f"Résultat non affiché ici pour ne pas surcharger le contexte."
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
    si journal_outils_historique va remplacer les plus anciens par un
    rappel. Utilise par core/main.py pour proposer rappeler_resultat_outil
    au modele seulement quand il peut en avoir besoin."""
    return sum(len(t) for _, _, t in _blocs_outils(historique)) > SEUIL_CARACTERES_OUTILS_HISTORIQUE


def _blocs_a_envoyer(historique, mentionner_outil_rappel=True):
    """[(index_message, texte)] des resultats d'outils a montrer au modele, dans l'ordre
    chronologique, apres allegement des plus anciens au-dela du budget."""
    blocs = _blocs_outils(historique)

    if not blocs:
        return []

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
        # Les outils du dernier message qui en porte restent toujours entiers : c'est le
        # travail en cours, le remplacer par un rappel ferait repartir le modele de zero.
        dernier_idx = blocs[-1][0]
        allege = []
        for idx, o, texte in anciens:
            if idx == dernier_idx:
                allege.append((idx, o, texte))
                continue
            rappel = _pointeur_outil(o, mentionner_outil_rappel)
            if len(texte) > len(rappel) + _MARGE_MIN_REMPLACEMENT:
                allege.append((idx, o, rappel))
            else:
                allege.append((idx, o, texte))
        blocs = allege + recents

    return [(idx, texte) for idx, _o, texte in blocs]


_ENTETE_JOURNAL = (
    "MÉMOIRE DE TRAVAIL (interne). Voici les résultats des outils que tu as déjà utilisés plus tôt "
    "dans cette conversation. Ce sont des informations de contexte, pas des messages : appuie-toi "
    "dessus pour répondre, mais ne les recopie jamais et ne reproduis jamais cette présentation "
    "dans ta réponse."
)

# Nombre de caracteres du debut d'une reponse repris pour situer ses outils dans le journal.
_LONGUEUR_REPERE = 80


def journal_outils_historique(historique, mentionner_outil_rappel=True):
    """
    `historique` : liste de dicts {role, content, outils?} tels qu'envoyes par le frontend
    (voir api/chat.py:MessageHistorique). Renvoie le texte du journal des outils deja utilises
    dans cette conversation, a ajouter au message systeme, ou une chaine vide si aucun message
    n'a d'outils. Chaque groupe d'outils est rattache a la reponse assistant qui l'a produit
    (son numero d'ordre et le debut de son texte), pour que le modele retrouve a quoi il a servi.
    N'altere jamais l'original.
    """
    blocs = _blocs_a_envoyer(historique, mentionner_outil_rappel)
    if not blocs:
        return ""

    par_index = {}
    for idx, texte in blocs:
        par_index.setdefault(idx, []).append(texte)

    numeros = {}
    n = 0
    for i, m in enumerate(historique or []):
        if m.get("role") == "assistant":
            n += 1
            numeros[i] = n

    parties = [_ENTETE_JOURNAL]
    for idx in sorted(par_index):
        debut = " ".join((historique[idx].get("content") or "").split())[:_LONGUEUR_REPERE]
        repere = f"Outils utilisés pendant ta réponse n°{numeros[idx]}"
        if debut:
            repere += f" (elle commençait par : {debut})"
        parties.append(repere + "\n\n" + "\n\n".join(par_index[idx]))
    return "\n\n".join(parties)


def historique_texte_seul(historique):
    """
    Historique tel qu'envoye au modele : meme longueur, memes roles, uniquement role et
    content. Les resultats d'outils n'y figurent plus (voir journal_outils_historique), donc un
    message assistant ne contient que ce que l'assistant a reellement dit.
    """
    return [{"role": m["role"], "content": m["content"]} for m in (historique or [])]
