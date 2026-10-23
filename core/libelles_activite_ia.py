"""
Libellés de la timeline du chat écrits par l'IA elle-même (23/10/2026, demande de
Bourama). Chaque outil proposé à l'IA reçoit un paramètre optionnel, dans lequel elle
décrit en une courte phrase ce qu'elle fait pour l'utilisateur (« Je cherche des vidéos
sur les dérivées »), dans la langue de la conversation.

Règles de la base posée ici :
- Le paramètre est optionnel : sans phrase valable, le texte fixe habituel s'affiche
  (voir profils_agents._nom_lisible), comme avant.
- Le paramètre n'est jamais transmis à l'outil lui-même (voir mcp_tools.appeler_outil).
- La phrase est nettoyée avant affichage (longueur, retours à la ligne, tirets doubles).
- Elle ne sert qu'à la timeline. Les confirmations d'actions sensibles gardent le texte
  fixe : l'utilisateur doit approuver ce que l'action fait vraiment, pas la description
  que l'IA en donne.
- Les phrases ne sont jamais passées par la table de traduction : l'IA les écrit déjà
  dans la bonne langue.
"""
import json
import re

PARAMETRE_LIBELLE_OUTIL = "libelle_activite"
LONGUEUR_MAX_LIBELLE = 90

_DESCRIPTION_PARAMETRE = (
    "Optionnel mais à toujours remplir. Une courte phrase (moins de 12 mots) à la première "
    "personne qui dit à l'utilisateur ce que tu fais en ce moment, avec son sujet réel, "
    "écrite dans la langue dans laquelle il t'écrit. Sans nom d'outil, sans nom de fichier, "
    "sans jargon technique, sans point final. "
    "Exemples : « Je cherche des vidéos sur les dérivées », « Je lis ton cours de chimie », "
    "« I'm looking for videos on derivatives »."
)


def schema_avec_libelle(schema):
    """Ajoute le paramètre de libellé, en premier, au schéma d'un outil (sans toucher à l'original)."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return schema
    proprietes = schema.get("properties") or {}
    if not isinstance(proprietes, dict) or PARAMETRE_LIBELLE_OUTIL in proprietes:
        return schema
    return {
        **schema,
        "properties": {
            PARAMETRE_LIBELLE_OUTIL: {"type": "string", "description": _DESCRIPTION_PARAMETRE},
            **proprietes,
        },
    }


def nettoyer_libelle(valeur):
    """Phrase prête à afficher, ou None si elle n'est pas utilisable."""
    if not isinstance(valeur, str):
        return None
    texte = re.sub(r"[\x00-\x1f\x7f]+", " ", valeur)
    texte = re.sub(r"[`<>{}\[\]]", "", texte)
    texte = re.sub(r"\s*(--+|—|–)\s*", ", ", texte)
    texte = re.sub(r"\s+", " ", texte).strip(" ,.;:!…")
    if len(texte) > LONGUEUR_MAX_LIBELLE:
        texte = texte[:LONGUEUR_MAX_LIBELLE].rsplit(" ", 1)[0].strip(" ,.;:!…")
    if len(texte) < 3 or not re.search(r"[^\W\d_]", texte):
        return None
    return texte


def libelle_ia_de_l_appel(appel):
    """Phrase écrite par l'IA pour cet appel (dict avec 'arguments' en JSON), ou None."""
    try:
        arguments = json.loads(appel.get("arguments") or "{}")
    except Exception:
        return None
    if not isinstance(arguments, dict):
        return None
    return nettoyer_libelle(arguments.get(PARAMETRE_LIBELLE_OUTIL))


def arguments_sans_libelle(arguments_json):
    """
    Arguments en JSON sans la phrase de libellé, pour comparer deux appels : sans ça, la
    détection d'appels identiques répétés ne verrait jamais deux appels pareils, puisque
    la phrase change d'un appel à l'autre.
    """
    try:
        arguments = json.loads(arguments_json or "{}")
    except Exception:
        return arguments_json
    if not isinstance(arguments, dict) or PARAMETRE_LIBELLE_OUTIL not in arguments:
        return arguments_json
    arguments = {k: v for k, v in arguments.items() if k != PARAMETRE_LIBELLE_OUTIL}
    return json.dumps(arguments, ensure_ascii=False, sort_keys=True)


def champs_timeline_appel(appel, libelle_fixe):
    """
    (nom_lisible, texte_en_cours, texte_termine, libelle_ia) pour la timeline : la phrase
    de l'IA si elle est valable, sinon le texte fixe habituel (`libelle_fixe`).
    """
    phrase = libelle_ia_de_l_appel(appel)
    if phrase:
        return phrase, f"{phrase}...", phrase, True
    return libelle_fixe, f"{libelle_fixe}...", f"{libelle_fixe} effectuée", False
