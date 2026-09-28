"""
Comparaison de texte simple et gratuite (aucun appel modele), partagee par
tout ce qui allege ou retrouve l'historique d'une conversation :
core/historique_conversation.py, core/outils_rappel_historique.py,
core/outils_rappel_resultats.py.

Ajoute le 28/09/2026 apres verification finale : la premiere version
comparait de simples mots separes par des espaces, donc des mots vides
comme "de", "la", "a", "et" faisaient "correspondre" presque tous les
messages a n'importe quel sujet. Ici, seuls les mots porteurs de sens sont
compares : accents normalises, ponctuation retiree, mots courts et mots
vides ecartes.
"""

import re
import unicodedata

# Mots trop courants pour dire quoi que ce soit du sujet d'un message
# (francais surtout, quelques mots anglais tres frequents). Les mots de
# moins de 4 lettres sont deja ecartes par la longueur minimale ci-dessous,
# cette liste ne contient donc que des mots de 4 lettres ou plus.
_MOTS_VIDES = frozenset("""
avec sans pour dans chez vers sous entre depuis pendant selon contre
mais donc puis alors ainsi aussi encore toujours jamais deja bien tres trop
plus moins autre autres meme memes tout tous toute toutes chaque quel quelle
quels quelles quoi dont ceci cela celui celle ceux celles cette ces mon ton son
notre votre leur leurs nous vous ils elles elle lui
etre avoir fait faire faut faudrait peut peux veux veut voir vois dit dire
suis sont etait etaient sera seront serait soit ete ont avez avons avait avaient
sera comme quand comment pourquoi parce quel
oui non merci bonjour salut svp stp voila ok
peux pouvez pourrais pourriez voudrais voulez
cest jai jen nest nai
that this with from have what when your they them then than there their would could should about
""".split())

_LONGUEUR_MIN = 4


def _normaliser(texte):
    texte = unicodedata.normalize("NFKD", (texte or "").lower())
    return "".join(c for c in texte if not unicodedata.combining(c))


def mots_significatifs(texte):
    """
    Ensemble des mots porteurs de sens d'un texte : minuscules, sans accents,
    sans ponctuation, au moins 4 lettres, hors mots vides, pluriel simple
    retire ("cours" et "cour" ne se rejoignent pas, mais "notions" et "notion"
    oui). Jamais d'appel modele.
    """
    resultat = set()
    for mot in re.findall(r"[a-z0-9]+", _normaliser(texte)):
        if len(mot) < _LONGUEUR_MIN or mot in _MOTS_VIDES:
            continue
        if len(mot) > 4 and mot.endswith(("s", "x")):
            mot = mot[:-1]
        resultat.add(mot)
    return resultat


def sujet_correspond(mots_sujet, mots_message):
    """
    Vrai si un message parle du sujet decrit par `mots_sujet` (resultat de
    mots_significatifs sur la description du sujet). Regle volontairement
    prudente : au moins deux mots significatifs en commun, et au moins la
    moitie des mots du sujet, pour qu'un mot isole qui revient par hasard
    ne suffise jamais a faire archiver un message. Un sujet decrit par un
    seul mot significatif ne correspond a rien : trop vague pour agir
    dessus sans risque.
    """
    if len(mots_sujet) < 2:
        return False
    communs = len(mots_sujet & mots_message)
    return communs >= 2 and communs * 2 >= len(mots_sujet)


def chevauchement_fort(mots_a, mots_b, minimum=3):
    """Vrai si deux textes partagent au moins `minimum` mots significatifs
    (utilise pour reconnaitre qu'un vieux message parle encore du meme sujet
    que les echanges recents)."""
    return len(mots_a & mots_b) >= minimum
