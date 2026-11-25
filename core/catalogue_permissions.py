"""
Liste des outils d'une application pour la page "Permissions des outils" (25/11/2026).

Deux sources :
- application connectée (Notion, GitHub, Vercel...) : le catalogue du chat, outils dont le groupe est
  cette application. Un outil est "écriture" s'il est dans OUTILS_SENSIBLES (une clé "outil:action" donne
  une ligne par action), sinon "lecture" ;
- serveur MCP personnalisé : ses outils découverts ; "lecture" quand le serveur ou le nom le dit
  (est_outil_non_sensible), sinon "écriture".

La classification est pure (testable sans réseau) : seules les deux fonctions `lister_*` appellent les serveurs.
"""

import json
import logging

from core.permissions_outils import ECRITURE, LECTURE, groupe_de_outil


def classer_outils_application(groupe, noms, outils_sensibles, nom_lisible):
    """[{"cle", "nom_lisible", "type"}] pour les outils `noms` de ce groupe.

    `nom_lisible(nom, action)` donne le texte affiché (action peut être None)."""
    resultat = {}
    for nom in noms:
        if groupe_de_outil(nom) != groupe:
            continue
        actions = sorted(c.split(":", 1)[1] for c in outils_sensibles if c.startswith(f"{nom}:"))
        if nom in outils_sensibles:
            resultat[nom] = {"cle": nom, "nom_lisible": nom_lisible(nom, None), "type": ECRITURE}
        elif actions:
            # Outil à plusieurs actions : une ligne par action sensible, les autres actions restent en lecture.
            resultat[nom] = {"cle": nom, "nom_lisible": nom_lisible(nom, None), "type": LECTURE}
            for action in actions:
                cle = f"{nom}:{action}"
                resultat[cle] = {"cle": cle, "nom_lisible": nom_lisible(nom, action), "type": ECRITURE}
        else:
            resultat[nom] = {"cle": nom, "nom_lisible": nom_lisible(nom, None), "type": LECTURE}
    return list(resultat.values())


def classer_outils_serveur(groupe, elements, est_non_sensible):
    """Même résultat pour un serveur personnalisé. `elements` : dicts avec "nom" (nom exposé) et "label"."""
    resultat = []
    vus = set()
    for element in elements:
        nom = element.get("nom")
        if not nom or nom in vus or groupe_de_outil(nom) != groupe:
            continue
        vus.add(nom)
        resultat.append({
            "cle": nom,
            "nom_lisible": element.get("label") or nom,
            "type": LECTURE if est_non_sensible(nom) else ECRITURE,
        })
    return resultat


def lister_outils_application(groupe, user_id, get_secret):
    """Outils d'une application connectée. Lève l'erreur si le catalogue est injoignable."""
    from core.constantes_agent import AGENT_ID_PAR_DEFAUT
    from core.mcp_tools import lister_outils_autorises_pour_agent
    from core.profils_agents import _nom_lisible_appel
    from core.registre_outils import OUTILS_SENSIBLES

    outils_llm, _ = lister_outils_autorises_pour_agent(get_secret, user_id, AGENT_ID_PAR_DEFAUT)
    noms = [o["function"]["name"] for o in outils_llm]

    def libelle(nom, action):
        arguments = json.dumps({"action": action}) if action else "{}"
        try:
            return _nom_lisible_appel({"name": nom, "arguments": arguments}) or nom
        except Exception:
            return nom

    return classer_outils_application(groupe, noms, OUTILS_SENSIBLES, libelle)


def serveur_perso_appartient(groupe, user_id):
    """True si ce groupe "custommcp_xxxxxx" est bien un serveur de cette personne."""
    from connexions.mcp_personnalises import _SUPABASE
    from core.permissions_outils import groupe_serveur_perso

    lignes = _SUPABASE.table("mcp_personnalises").select("id").eq("user_id", user_id).execute().data or []
    return any(groupe_serveur_perso(ligne["id"]) == groupe for ligne in lignes)


def lister_outils_serveur(groupe, user_id):
    """Outils découverts d'un serveur personnalisé (liste vide s'il est injoignable : la page l'indique)."""
    from connexions.mcp_personnalises import est_outil_non_sensible, lister_outils_pour_utilisateur

    try:
        elements = lister_outils_pour_utilisateur(user_id, attente_max=8.0)
    except Exception as e:
        logging.warning(f"Outils du serveur perso illisibles pour la page permissions ({type(e).__name__}).")
        elements = []
    return classer_outils_serveur(groupe, elements, est_outil_non_sensible)
