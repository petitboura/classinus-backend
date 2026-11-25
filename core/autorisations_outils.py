"""
Autorisations permanentes des actions sensibles (bouton "Toujours autoriser",
demande de Bourama, 31/10/2026).

Quand la personne clique sur "Toujours autoriser" au lieu de "Confirmer", la
clé de l'action (le nom de l'outil, ou "outil:action" pour les outils à
plusieurs actions) est gardée en base pour CETTE personne. Les fois suivantes,
cette action précise ne redemande plus rien. Rien d'autre n'est autorisé :
une autre action du même service redemande toujours confirmation.

Depuis le 24/11/2026 ces réglages vivent dans la table permissions_outils, avec
deux états de plus (demander, bloquer) et des réglages par catégorie d'outils :
voir core/permissions_outils.py, qui porte toute la logique. Ce fichier garde
les mêmes noms de fonctions pour le bouton du chat et l'écran Applications
connectées d'avant : "Toujours autoriser" revient à écrire l'état "autoriser",
et "Retirer" supprime le réglage (la valeur par défaut s'applique de nouveau).
Les anciennes tables (autorisations_outils_permanentes et
mcp_personnalises.autoriser_non_sensibles) ont été reprises par la migration
2026_11_24_permissions_outils.sql et ne sont plus lues.
"""

import logging

from core.permissions_outils import (  # noqa: F401  (appli_de_cle est réexporté pour l'existant)
    AUTORISER,
    LONGUEUR_MAX_CLE,
    LONGUEUR_MAX_NOM,
    appli_de_cle,
    charger_permissions,
    ecrire_etat,
    lire_lignes,
    retirer_reglage,
)
from registre_outils import (
    AUTORISATION_PERMANENTE_INTERDITE,
    OUTILS_SENSIBLES,
    est_outil_sensible_serveur_personnel,
)


def cle_valide(cle):
    """True seulement pour une action qui demande normalement une confirmation."""
    if not isinstance(cle, str) or not cle or len(cle) > LONGUEUR_MAX_CLE:
        return False
    if cle in AUTORISATION_PERMANENTE_INTERDITE:
        return False
    return cle in OUTILS_SENSIBLES or est_outil_sensible_serveur_personnel(cle)


def charger_autorisations(user_id):
    """Réglages de cette personne (objet Permissions). Vide en cas de panne : les valeurs par défaut
    s'appliquent donc, c'est-à-dire qu'on redemande pour les actions sensibles."""
    return charger_permissions(user_id)


def lister_autorisations(user_id):
    """Actions "toujours autorisées" pour l'ancien écran Applications connectées. Lève l'erreur de la base.

    Seuls les réglages d'outils à l'état "autoriser" sont listés : les réglages de catégorie et les
    outils à confirmer ou bloqués se gèrent dans la nouvelle section Permissions des outils."""
    lignes = [
        ligne for ligne in lire_lignes(user_id)
        if ligne.get("etat") == AUTORISER and not ligne["cle"].startswith("categorie:")
    ]
    return [{**ligne, "nom_lisible": _nom_lisible_a_afficher(ligne), "appli": appli_de_cle(ligne["cle"])} for ligne in lignes]


def _nom_lisible_a_afficher(ligne):
    """Texte montré dans la liste. Un outil de serveur personnalisé garde son vrai nom : les lignes anciennes disaient toutes « Action sur <serveur> »."""
    cle = ligne["cle"]
    if cle.startswith("custommcp_"):
        try:
            from connexions.mcp_personnalises import libelle_depuis_cle_outil
            return libelle_depuis_cle_outil(cle) or ligne.get("nom_lisible")
        except Exception:
            pass
    return ligne.get("nom_lisible")


def enregistrer_autorisation(user_id, cle, nom_lisible):
    """Garde l'autorisation. False si la clé n'est pas une action sensible ou si la base échoue."""
    if not user_id or not cle_valide(cle):
        return False
    try:
        ecrire_etat(user_id, cle, AUTORISER, nom_lisible or cle)
        return True
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (écriture permissions_outils user={user_id} cle={cle}) : {e}")
        return False


def retirer_autorisation(user_id, cle):
    """Retire l'autorisation. Lève l'erreur de la base."""
    retirer_reglage(user_id, cle)
