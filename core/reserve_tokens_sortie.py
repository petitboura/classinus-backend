"""
Reserve de tokens de sortie demandee a chaque appel de modele de la boucle d'agent.

Le plafond de 4096 avait ete pose le 30/07/2026 pour Groq : Groq compare la reserve
demandee (pas l'usage reel) a sa limite par minute, donc 8192 faisait echouer certains
modeles gratuits des le depart. Muse Spark Open est servi par Baseten, pas par Groq, cette
contrainte ne le concerne pas : avec 4096 (reflexion comprise), ses reponses etaient coupees
en plein chantier (log TRONCATURE, finish_reason=length).

Muse Spark Open (01/11/2026, demande de Bourama) : 131072, la plus basse des limites de
sortie publiees par les fournisseurs (131K, 262K ou 1M selon la source). Le maximum
theorique de 1048576 est volontairement evite : il egale toute la fenetre de contexte, un
fournisseur peut donc refuser l'appel des que le prompt n'est pas vide. Seuls les tokens
reellement generes sont factures, la reserve ne coute rien.

Tous les modeles hors Groq (02/11/2026, demande de Bourama) : meme raisonnement, appliquee a
DeepSeek, modele principal de la cascade, qui recevait encore les 4096 pensees pour Groq. La
valeur est reglable sans toucher au code (RESERVE_TOKENS_SORTIE_HORS_GROQ dans
core/plafonds_reglables.py). Les modeles Claude, GPT, Gemini et Grok passent par leurs propres
adaptateurs, qui ignorent cette reserve : rien ne change pour eux.
"""

from core.plafonds_reglables import RESERVE_TOKENS_SORTIE_HORS_GROQ

# Reserve par modele, pour les modeles qui ne dependent pas des limites de Groq.
RESERVE_TOKENS_PAR_MODELE = {
    "muse-spark-open": 131072,
}

RESERVE_TOKENS_PRINCIPAL_GROQ = 8192
RESERVE_TOKENS_DEFAUT = 4096


def reserve_tokens_sortie(modele, modele_principal_groq, modeles_groq=None):
    """Nombre de tokens de sortie a reserver pour ce modele.

    `modeles_groq` : les modeles de secours de la cascade Groq (GROQ_FALLBACKS), fournis par
    l'appelant car ce module ne peut pas importer constantes_agent (il depend du reseau et de
    la base). Ces modeles gardent des reserves basses a cause des limites par minute de Groq.
    Tout autre modele a un nom reel (DeepSeek par exemple) recoit la reserve large.
    Sans cette liste (None), on ne sait pas distinguer un modele Groq d'un autre : la valeur
    prudente d'avant s'applique, jamais la reserve large.
    """
    if modele in RESERVE_TOKENS_PAR_MODELE:
        return RESERVE_TOKENS_PAR_MODELE[modele]
    if modele == modele_principal_groq:
        return RESERVE_TOKENS_PRINCIPAL_GROQ
    if not modele or modeles_groq is None or modele in modeles_groq:
        return RESERVE_TOKENS_DEFAUT
    return RESERVE_TOKENS_SORTIE_HORS_GROQ
