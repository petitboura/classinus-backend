"""
Efforts de réflexion proposés pour chaque modèle du sélecteur (20/10/2026, demande de
Bourama : adapter le raisonnement et l'effort à chaque fournisseur, et le retirer là où ce
n'est pas possible).

Chaque fournisseur a son propre vocabulaire pour dire « réfléchis plus ou moins » :
    DeepSeek : reasoning_effort  none, low, high, max
    Grok     : reasoning.effort  none, low, medium, high (4.3) ; low, medium, high, xhigh (4.7)
    GPT      : reasoning.effort  none, low, medium, high, xhigh, max (selon le modèle)
    Claude   : output_config.effort  low, medium, high, xhigh, max
    Gemini   : thinking_level  low, medium, high
    Meta     : reasoning.effort  minimal, low, medium, high, xhigh, max (vérifié dans la doc officielle Meta le 29/10/2026 : "none" refusé, "max" confirmé pour Muse Spark 1.3 et Muse Wonder)

Ce module est la source unique de cette liste : le backend s'en sert pour revalider l'effort
reçu du frontend (jamais de confiance dans le client), et le frontend la reçoit avec chaque
modèle (champs efforts et effort_defaut) pour n'afficher que les niveaux possibles. Un modèle
sans aucun effort possible est simplement présenté sans réglage d'effort.

Les valeurs viennent de la documentation de chaque fournisseur (vérifiée le 20/10/2026). Un
modèle inconnu reçoit la liste prudente de son fournisseur (low, medium, high), valable
partout, pour ne jamais envoyer une valeur refusée par l'API quand un identifiant change
dans Supabase.
"""

try:
    import fournisseurs_llm
except ImportError:
    from core import fournisseurs_llm

# Ordre d'affichage, du plus léger au plus profond.
ORDRE_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")

# Liste prudente par fournisseur, utilisée quand le modèle n'a pas de règle plus précise.
EFFORTS_PAR_FOURNISSEUR = {
    "deepseek": ("none", "low", "high", "max"),
    "claude": ("low", "medium", "high"),
    "gpt": ("low", "medium", "high"),
    "gemini": ("low", "medium", "high"),
    "grok": ("low", "medium", "high"),
    "meta": ("minimal", "low", "medium", "high", "xhigh", "max"),
}

# Règles précises, par début d'identifiant de modèle. La première qui correspond gagne.
EFFORTS_PAR_PREFIXE_MODELE = (
    ("claude-sonnet-5-5", ("low", "medium", "high", "xhigh", "max")),
    ("claude-opus-5-5", ("low", "medium", "high", "xhigh", "max")),
    ("gpt-6-luna", ("none", "low", "medium", "high", "xhigh", "max")),
    ("gpt-6-astra", ("low", "medium", "high", "xhigh", "max")),
    ("gpt-6.1-sol", ("low", "medium", "high", "xhigh", "max")),
    ("gpt-6-sol", ("low", "medium", "high", "xhigh", "max")),
    ("grok-4.7", ("low", "medium", "high", "xhigh")),
    ("grok-4.3", ("none", "low", "medium", "high")),
    ("muse-spark-1.3", ("minimal", "low", "medium", "high", "xhigh", "max")),
    ("muse-wonder-1.0", ("minimal", "low", "medium", "high", "xhigh", "max")),
    # Muse Spark Open (30/10/2026) : servi par Baseten, qui ne documente pas de reglage d'effort
    # pour ce modele (reflexion toujours active). Liste vide : aucun reglage, rien n'est envoye.
    ("muse-spark-open", ()),
)

# Fournisseurs dont les modèles passent par un adaptateur d'outils (voir
# core/clients_outils_llm.py). DeepSeek garde son propre chemin.
DISTRIBUTEURS_AVEC_ADAPTATEUR = ("claude", "gpt", "gemini", "grok", "meta")

# Effort choisi quand rien de valide n'a été demandé : le plus rapide qui existe, comme le
# défaut historique de DeepSeek (DEEPSEEK_REASONING_EFFORT = "low").
EFFORT_PRIORITAIRE_PAR_DEFAUT = ("low", "medium", "high")


def distributeur_du_modele(modele_id):
    """Fournisseur d'un modèle, ou None s'il est inconnu."""
    if not modele_id:
        return None
    distributeur = fournisseurs_llm.distributeur_pour_modele_id(modele_id)
    if distributeur:
        return distributeur
    # Identifiants de la cascade qui ne sont pas dans le sélecteur.
    if str(modele_id).startswith("deepseek"):
        return "deepseek"
    return None


def efforts_pour_modele(modele_id, distributeur=None):
    """Efforts possibles pour ce modèle, dans l'ordre d'affichage. Vide : pas de réglage."""
    for prefixe, efforts in EFFORTS_PAR_PREFIXE_MODELE:
        if str(modele_id or "").startswith(prefixe):
            return list(efforts)
    distributeur = distributeur or distributeur_du_modele(modele_id)
    return list(EFFORTS_PAR_FOURNISSEUR.get(distributeur, ()))


def effort_defaut(efforts):
    """Effort par défaut parmi ceux d'un modèle, None si le modèle n'en a pas."""
    for effort in EFFORT_PRIORITAIRE_PAR_DEFAUT:
        if effort in efforts:
            return effort
    return efforts[0] if efforts else None


def effort_valide_pour_modele(modele_id, effort, distributeur=None):
    """
    Effort à envoyer à l'API : celui demandé s'il existe pour ce modèle, sinon le défaut du
    modèle, sinon None (le modèle n'a pas de réglage, rien n'est envoyé).
    """
    efforts = efforts_pour_modele(modele_id, distributeur)
    if effort in efforts:
        return effort
    return effort_defaut(efforts)


def est_modele_avec_adaptateur(modele_id):
    """Vrai pour un modèle Claude, GPT, Gemini, Grok ou Meta du sélecteur."""
    return distributeur_du_modele(modele_id) in DISTRIBUTEURS_AVEC_ADAPTATEUR
