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
"""

# Reserve par modele, pour les modeles qui ne dependent pas des limites de Groq.
RESERVE_TOKENS_PAR_MODELE = {
    "muse-spark-open": 131072,
}

RESERVE_TOKENS_PRINCIPAL_GROQ = 8192
RESERVE_TOKENS_DEFAUT = 4096


def reserve_tokens_sortie(modele, modele_principal_groq):
    """Nombre de tokens de sortie a reserver pour ce modele."""
    if modele in RESERVE_TOKENS_PAR_MODELE:
        return RESERVE_TOKENS_PAR_MODELE[modele]
    if modele == modele_principal_groq:
        return RESERVE_TOKENS_PRINCIPAL_GROQ
    return RESERVE_TOKENS_DEFAUT
