"""
Recherche d'outils par mots clés (BM25), sans LLM ni appel réseau.

Créé le 05/09/2026 (demande Bourama) : étape 1 du chantier "demander_outils"
-- un outil interne permettant au grand modèle de demander, en pleine tâche,
des outils qu'il n'a pas dans sa sélection courante, décrits en langage
libre. Cette fonction ne fait QUE la partie recherche : comparer un texte
libre aux descriptions d'une liste d'outils candidats, et renvoyer les plus
pertinents. Elle ne sait rien de la conversation, du modèle, ni de comment
les outils sont ensuite branchés -- ça, c'est la suite du chantier (étapes
2 et 3).

Choix BM25 plutôt que la recherche par sens (pgvector, comme pour la
bibliothèque) : le catalogue total d'outils de Classinus reste petit (quelques
dizaines), donc pas besoin d'un appel réseau à Gemini pour vectoriser à
chaque demande. BM25 tourne entièrement en mémoire, instantanément, sans
dépendance externe ni nouvelle table Supabase à maintenir.

Implémentation manuelle (pas de librairie type rank_bm25) pour ne rien
ajouter aux dépendances du projet : l'algorithme est court et stable, pas
besoin d'un paquet externe pour ça.
"""

import math
import re
import unicodedata

# Constantes BM25 standard (k1 = saturation de la fréquence des mots,
# b = poids de la longueur du document). Valeurs par défaut habituelles,
# pas de raison d'en changer tant qu'on n'a pas mesuré de mauvais résultats
# sur le catalogue réel de Clovis.
_BM25_K1 = 1.5
_BM25_B = 0.75

# Sous ce score, un outil n'est pas considéré comme pertinent. Ajustable
# sans casser la fonction : voir seuil_pertinence en paramètre de
# rechercher_outils_pertinents().
SEUIL_PERTINENCE_DEFAUT = 0.15

# 21/10/2026 (demande Bourama) : demander_outils doit toujours presenter un
# minimum d'outils (5), meme quand peu d'outils depassent le seuil, pour que le
# modele ne reste pas bloque sur un "rien trouve". Plus de maximum a 5 : le
# plafond ci-dessous n'est qu'un garde-fou pour qu'un besoin vague ne deverse
# pas des dizaines d'outils dans le contexte. Les outils ajoutes ensuite par
# les groupes et les dependances (completion_outils.py) ne comptent dans aucun
# des deux.
MINIMUM_OUTILS_DEFAUT = 5
PLAFOND_OUTILS_DEFAUT = 15

# Mots trop courants en français pour aider à distinguer un outil d'un
# autre (déterminants, prépositions...). Liste volontairement courte :
# le but est juste d'éviter que ces mots dominent le score, pas de faire
# un vrai traitement linguistique.
_MOTS_VIDES = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "a",
    "au", "aux", "pour", "sur", "dans", "avec", "sans", "par", "en",
    "ce", "cette", "ces", "il", "elle", "je", "tu", "on", "nous", "vous",
    "qui", "que", "quoi", "dont", "est", "sont", "faire", "fait",
}


def _normaliser(texte):
    """Minuscule, accents retirés, ponctuation transformée en espaces."""
    texte = texte.lower()
    texte = unicodedata.normalize("NFD", texte)
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = re.sub(r"[^a-z0-9\s]", " ", texte)
    return texte


def _tokeniser(texte):
    """Découpe un texte normalisé en mots, mots vides retirés."""
    return [mot for mot in _normaliser(texte).split() if mot and mot not in _MOTS_VIDES]


def _texte_outil(outil, libelle_supplementaire=""):
    """
    Concatène nom et description d'un outil candidat pour la recherche.
    `outil` est un dict au format outils_pour_llm existant :
    {"type": "function", "function": {"name": ..., "description": ..., ...}}.

    `libelle_supplementaire` (ajouté le 10/09/2026, demande Bourama) : texte
    optionnel fourni par l'appelant, utilisé UNIQUEMENT pour enrichir la
    recherche -- il n'entre pas dans l'outil renvoyé, seulement dans le
    document comparé au besoin exprimé. Sert notamment pour les outils
    d'origine externe (Tavily, Notion, Google Drive...) dont le nom et la
    description techniques sont en anglais et ne recoupent donc jamais un
    besoin exprimé en français par le grand modèle (ex. "tavily_search"
    face à "chercher sur internet").
    """
    fonction = outil.get("function", {})
    nom = fonction.get("name", "") or ""
    description = fonction.get("description", "") or ""
    # Le nom compte double : souvent plus révélateur que la description
    # (ex. "gerer_document_bibliotheque" est déjà très parlant), sans pour
    # autant écraser le poids de la description.
    return f"{nom} {nom} {description} {libelle_supplementaire}".strip()


def _selectionner(classes, outils_candidats, seuil_pertinence, max_resultats, minimum_resultats, completer_hors_score):
    """
    `classes` : [(outil, score entre 0 et 1)] des outils avec un score au dessus
    de zéro, du plus au moins pertinent (liste vide si aucun mot en commun).
    Garde ceux au dessus du seuil (plafond max_resultats), puis complète
    jusqu'au minimum, voir rechercher_outils_pertinents.
    """
    if not classes and not completer_hors_score:
        return []
    retenus = [outil for outil, score in classes if score >= seuil_pertinence][:max_resultats]
    minimum = min(minimum_resultats, len(outils_candidats))
    if len(retenus) < minimum:
        for outil, _score in classes:
            if len(retenus) >= minimum:
                break
            if not any(outil is deja for deja in retenus):
                retenus.append(outil)
    if completer_hors_score and len(retenus) < minimum:
        for outil in outils_candidats:
            if len(retenus) >= minimum:
                break
            if not any(outil is deja for deja in retenus):
                retenus.append(outil)
    return retenus


def rechercher_outils_pertinents(texte_requete, outils_candidats, seuil_pertinence=SEUIL_PERTINENCE_DEFAUT, max_resultats=PLAFOND_OUTILS_DEFAUT, libelles_supplementaires=None, minimum_resultats=MINIMUM_OUTILS_DEFAUT, completer_hors_score=False):
    """
    Compare `texte_requete` (la phrase libre écrite par le grand modèle,
    ex. "il me faudrait un outil pour lire un fichier PDF") aux
    descriptions des outils de `outils_candidats`, et renvoie ceux jugés
    pertinents, du plus au moins pertinent.

    Args:
        texte_requete: texte libre décrivant le besoin.
        outils_candidats: liste de dicts au format outils_pour_llm (voir
            core/mcp_tools.py, lister_outils_autorises_pour_agent). Doit
            déjà être filtrée en amont pour ne contenir QUE les outils pas
            encore disponibles ce tour-ci -- cette fonction ne fait aucun
            tri là dessus, ce n'est pas son rôle.
        seuil_pertinence: score BM25 normalisé minimum (entre 0 et 1) pour
            qu'un outil soit retenu. Par défaut SEUIL_PERTINENCE_DEFAUT.
        max_resultats: plafond de sécurité d'outils renvoyés, même si plus
            d'outils dépassent le seuil (voir PLAFOND_OUTILS_DEFAUT).
        minimum_resultats: nombre minimum d'outils renvoyés (voir
            MINIMUM_OUTILS_DEFAUT). Si moins d'outils dépassent le seuil, on
            complète avec les suivants les mieux classés (score au dessus de
            zéro). Jamais plus que le nombre d'outils candidats.
        completer_hors_score: si Vrai et que le minimum n'est toujours pas
            atteint (aucun mot en commun, ou trop peu d'outils avec un score),
            complète avec les autres candidats dans leur ordre d'origine.
            À n'activer que lorsque les candidats ont déjà été limités à une
            catégorie : sur tout le catalogue, ce serait arbitraire.
        libelles_supplementaires: dict optionnel {nom_outil: texte français}
            utilisé seulement pour la comparaison (voir _texte_outil), pas
            renvoyé dans le résultat. Sert à combler les outils externes
            dont le nom/la description technique est en anglais.

    Returns:
        Liste de dicts, sous-ensemble de `outils_candidats`, triée du plus
        au moins pertinent. Liste vide si `outils_candidats` est vide ou
        `texte_requete` vide, ou si aucun candidat n'a de score et que
        `completer_hors_score` est faux.
    """
    if not texte_requete or not outils_candidats:
        return []

    tokens_requete = _tokeniser(texte_requete)
    if not tokens_requete:
        return _selectionner([], outils_candidats, seuil_pertinence, max_resultats, minimum_resultats, completer_hors_score)

    libelles_supplementaires = libelles_supplementaires or {}
    documents = [
        _tokeniser(_texte_outil(outil, libelles_supplementaires.get(outil.get("function", {}).get("name", ""), "")))
        for outil in outils_candidats
    ]
    nb_documents = len(documents)
    longueur_moyenne = sum(len(d) for d in documents) / nb_documents

    # Fréquence documentaire : dans combien de documents chaque mot de la
    # requête apparaît au moins une fois.
    freq_documentaire = {}
    for mot in set(tokens_requete):
        freq_documentaire[mot] = sum(1 for d in documents if mot in d)

    scores_bruts = []
    for document in documents:
        longueur_doc = len(document) or 1
        score = 0.0
        for mot in tokens_requete:
            df = freq_documentaire.get(mot, 0)
            if df == 0:
                continue
            idf = math.log(1 + (nb_documents - df + 0.5) / (df + 0.5))
            freq_terme = document.count(mot)
            denominateur = freq_terme + _BM25_K1 * (1 - _BM25_B + _BM25_B * longueur_doc / longueur_moyenne)
            score += idf * (freq_terme * (_BM25_K1 + 1)) / denominateur if denominateur else 0.0
        scores_bruts.append(score)

    score_max = max(scores_bruts) if scores_bruts else 0.0
    if score_max <= 0:
        return _selectionner([], outils_candidats, seuil_pertinence, max_resultats, minimum_resultats, completer_hors_score)

    classes = [
        (outil, score / score_max)
        for outil, score in zip(outils_candidats, scores_bruts)
        if score > 0
    ]
    classes.sort(key=lambda paire: paire[1], reverse=True)

    return _selectionner(classes, outils_candidats, seuil_pertinence, max_resultats, minimum_resultats, completer_hors_score)
