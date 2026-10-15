"""
Identité de l'assistant (15/10/2026, demande de Bourama).

Le modèle ne dit plus qu'il est Classinus : Classinus est le nom de l'application. Il se
présente comme l'assistant de Classinus, propulsé par le fournisseur puis le modèle qui
répond réellement à ce message. Un seul bloc, pour tous les modèles et tous les modes.

Le bloc ne raconte pas au modèle qui il est (il le sait déjà), il lui dit seulement ce
qu'il ne peut pas savoir : le nom de l'application et la façon de se présenter.

Le modèle qui répond change selon la cascade (DeepSeek, puis Groq, puis Gemini) et selon
le choix de l'utilisateur dans le sélecteur de modèles. Le bloc est donc posé au moment de
chaque appel de modèle (voir core/main.py), jamais une fois pour toutes dans
_construire_system_prompt, qui ne sait pas encore quel modèle va répondre.
"""

# Nom affiché de chaque fournisseur du sélecteur de modèles (clé = distributeur de la
# table fournisseurs_llm de Supabase).
NOMS_FOURNISSEURS = {
    "claude": "Anthropic",
    "gpt": "OpenAI",
    "gemini": "Google",
    "deepseek": "DeepSeek",
}

# Modèles de la cascade (core/constantes_agent.py), qui ne sont pas tous dans la
# configuration du sélecteur. Clé = identifiant envoyé à l'API, valeur = (fournisseur,
# nom du modèle). À mettre à jour quand la cascade change.
MODELES_CASCADE = {
    "deepseek-v4-flash": ("DeepSeek", "DeepSeek V4 Flash"),
    "openai/gpt-oss-120b": ("OpenAI", "GPT-OSS 120B"),
    "openai/gpt-oss-20b": ("OpenAI", "GPT-OSS 20B"),
    "qwen/qwen3.6-27b": ("Alibaba", "Qwen 3.6 27B"),
    "llama-3.1-8b-instant": ("Meta", "Llama 3.1 8B"),
    "gemini-2.5-flash": ("Google", "Gemini 2.5 Flash"),
}

BLOC_IDENTITE = (
    "Tu es l'assistant de Classinus, propulsé par {fournisseur}, modèle {modele}. "
    "Classinus est le nom de l'application, pas le tien : ne dis jamais que tu es Classinus. "
    "Si on te demande qui tu es, réponds que tu es l'assistant de Classinus, propulsé par "
    "{fournisseur}, modèle {modele}."
)

# Modèle absent des deux listes : on ne devine rien, on le dit au modèle.
BLOC_IDENTITE_INCONNU = (
    "Tu es l'assistant de Classinus. Classinus est le nom de l'application, pas le tien : "
    "ne dis jamais que tu es Classinus. Tu ne sais pas quel fournisseur ni quel modèle te "
    "propulse. Si on te le demande, dis simplement que tu es l'assistant de Classinus et que "
    "tu ne connais pas ces détails."
)


def _depuis_configuration_selecteur(modele_id):
    """(fournisseur, nom du modèle) d'un modèle du sélecteur, ou None s'il n'y est pas."""
    try:
        # Même ordre d'import que core/main.py (module à plat d'abord), pour partager le
        # cache de configuration de fournisseurs_llm au lieu d'en créer un second.
        try:
            import fournisseurs_llm
        except ImportError:
            from core import fournisseurs_llm
        for distributeur, paliers in fournisseurs_llm._config_modeles()["modeles"].items():
            for info in paliers.values():
                if info["id"] == modele_id:
                    fournisseur = NOMS_FOURNISSEURS.get(distributeur) or distributeur
                    return fournisseur, info["label"]
    except Exception:
        # La configuration est illisible : on retombe sur le bloc sans nom plutôt que de
        # faire échouer la réponse.
        return None
    return None


def fournisseur_et_modele(modele_id):
    """(fournisseur, nom du modèle) du modèle donné, ou None s'il est inconnu."""
    if not modele_id:
        return None
    if modele_id in MODELES_CASCADE:
        return MODELES_CASCADE[modele_id]
    return _depuis_configuration_selecteur(modele_id)


def bloc_identite(modele_id):
    """Texte du bloc d'identité pour le modèle qui répond."""
    trouve = fournisseur_et_modele(modele_id)
    if trouve is None:
        return BLOC_IDENTITE_INCONNU
    fournisseur, modele = trouve
    return BLOC_IDENTITE.format(fournisseur=fournisseur, modele=modele)


def systeme_avec_identite(systeme, modele_id):
    """
    Prompt système avec le bloc d'identité en tête. En tête et non à la fin : le préfixe
    reste identique d'un message à l'autre pour un même modèle, ce qui garde le cache de
    prompt du fournisseur (voir le commentaire de _construire_system_prompt).
    """
    base = systeme or ""
    bloc = bloc_identite(modele_id)
    return (bloc + "\n\n" + base) if base else bloc


def message_systeme(systeme, modele_id):
    """Message {"role": "system"} prêt à remplacer le premier message d'une conversation."""
    return {"role": "system", "content": systeme_avec_identite(systeme, modele_id)}
