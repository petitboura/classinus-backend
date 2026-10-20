"""
Fabrique des clients avec outils pour les modèles Claude, GPT, Gemini et Grok (20/10/2026).

Chaque client expose le même appel que le SDK OpenAI (client.chat.completions.create), ce qui
permet à la boucle d'agent (core/boucle_agent.py:_agent_groq) de s'en servir sans rien changer :
outils, mémoire, demander_outils, confirmations, bouton Arrêter. DeepSeek garde son chemin
existant (client OpenAI vers api.deepseek.com, voir core/main.py).

Renvoie None quand le modèle n'est pas géré ici ou que la clé API du fournisseur est absente :
l'appelant retombe alors sur le chemin texte seul, comme avant.
"""

try:
    import fournisseurs_llm
    from efforts_modeles import DISTRIBUTEURS_AVEC_ADAPTATEUR, distributeur_du_modele
except ImportError:
    from core import fournisseurs_llm
    from core.efforts_modeles import DISTRIBUTEURS_AVEC_ADAPTATEUR, distributeur_du_modele


def modele_a_des_outils(modele_id):
    """
    Vrai si ce modèle du sélecteur reçoit les outils : DeepSeek (client OpenAI, voir core/main.py)
    ou Claude, GPT, Gemini et Grok (adaptateurs), à condition que la clé API du fournisseur existe.
    Sans clé, le modèle retombe sur le chemin texte seul.
    """
    distributeur = distributeur_du_modele(modele_id)
    if distributeur != "deepseek" and distributeur not in DISTRIBUTEURS_AVEC_ADAPTATEUR:
        return False
    return bool(fournisseurs_llm.cle_api_du_distributeur(distributeur))


def client_avec_outils(modele_id):
    """Client avec outils pour un modèle Claude, GPT, Gemini ou Grok, ou None (DeepSeek : voir core/main.py)."""
    if distributeur_du_modele(modele_id) not in DISTRIBUTEURS_AVEC_ADAPTATEUR or not modele_a_des_outils(modele_id):
        return None
    distributeur = distributeur_du_modele(modele_id)
    cle = fournisseurs_llm.cle_api_du_distributeur(distributeur)
    # Imports à la demande : un SDK absent ou cassé ne doit gêner que son fournisseur.
    if distributeur == "claude":
        try:
            from adaptateur_claude import ClientClaude
        except ImportError:
            from core.adaptateur_claude import ClientClaude
        return ClientClaude(cle)
    if distributeur == "gemini":
        try:
            from adaptateur_gemini import ClientGemini
        except ImportError:
            from core.adaptateur_gemini import ClientGemini
        return ClientGemini(cle)
    try:
        from adaptateur_responses import ClientResponses
    except ImportError:
        from core.adaptateur_responses import ClientResponses
    return ClientResponses(cle, "xai" if distributeur == "grok" else "openai")
