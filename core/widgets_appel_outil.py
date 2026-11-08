"""Appels d'outils lances depuis un widget MCP (chantier du 08/11/2026).

Un widget interactif (MCP Apps, Higgsfield par exemple) peut demander `tools/call`. Le widget est du
code tiers dans une iframe isolee : il ne parle jamais au serveur MCP lui-meme. Le frontend relaie la
demande vers la route authentifiee de api/widgets_outils.py, qui s'appuie sur ce module.

Garde-fous (tous appliques ICI, jamais confies au navigateur) :
- seul un outil du MEME serveur que celui qui a affiche le widget est appelable (meme prefixe, meme
  adresse dans la table de routage de la personne) ;
- les serveurs ajoutes par la personne, l'app telephone et les outils internes sont exclus ;
- la sensibilite est celle du chat (core/execution_outils.py::cle_autorisation_appel) : une lecture
  passe sans confirmation, une action qui modifie ou qui coute exige la confirmation, sauf
  "Toujours autoriser" deja accorde ;
- le resultat est rendu au widget sans enveloppe interne (widgets, galerie).
"""
import json
import re

from core.registre_outils import PREFIXES_SERVEURS_PERSONNELS

LONGUEUR_MAX_NOM = 200
_NOM_VALIDE = re.compile(r"^[A-Za-z0-9_.:\-]+$")
_DEBUTS_ERREUR = ("Erreur :", "Délai dépassé", "Action annulée")


class ErreurWidget(Exception):
    """Refus d'un appel de widget. `code` est un code stable de core/erreurs.py."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def prefixe_du_serveur(nom_outil_source):
    """Prefixe du serveur (ex. "higgsfield_") dont vient l'outil qui a affiche le widget, sinon None.

    Les serveurs ajoutes par la personne ("custommcp_") ne sont jamais relayes.
    """
    for prefixe in PREFIXES_SERVEURS_PERSONNELS:
        if prefixe != "custommcp_" and nom_outil_source.startswith(prefixe):
            return prefixe
    return None


def _nom_valide(nom):
    return isinstance(nom, str) and 0 < len(nom) <= LONGUEUR_MAX_NOM and bool(_NOM_VALIDE.match(nom))


def resoudre_appel(nom_outil_source, nom_reel, table_routage):
    """Nom expose (prefixe compris) de l'outil demande par le widget. Leve ErreurWidget si refus."""
    if not _nom_valide(nom_outil_source) or not _nom_valide(nom_reel):
        raise ErreurWidget("WIDGET_APPEL_REFUSE")
    prefixe = prefixe_du_serveur(nom_outil_source)
    if not prefixe:
        raise ErreurWidget("WIDGET_APPEL_REFUSE")
    route_source = table_routage.get(nom_outil_source)
    nom_expose = prefixe + nom_reel
    route_cible = table_routage.get(nom_expose)
    if not route_source or not route_cible:
        raise ErreurWidget("WIDGET_OUTIL_INTROUVABLE")
    for route in (route_source, route_cible):
        if route.get("custom_mcp") or route.get("via_app_telephone"):
            raise ErreurWidget("WIDGET_APPEL_REFUSE")
    if not route_source.get("url") or route_source.get("url") != route_cible.get("url"):
        raise ErreurWidget("WIDGET_APPEL_REFUSE")
    return nom_expose


def appel_au_format_chat(nom_expose, arguments):
    """Meme forme que les appels du chat, pour reutiliser leurs regles de sensibilite."""
    return {"name": nom_expose, "arguments": json.dumps(arguments or {}, ensure_ascii=False)}


def texte_pour_widget(resultat):
    """Texte d'origine du resultat, sans enveloppe interne (widgets, galerie d'images ou de videos)."""
    if not isinstance(resultat, str):
        return ""
    from core.ressources_ui import separer_ressources_ui

    texte, _ = separer_ressources_ui(resultat)
    if isinstance(texte, str) and texte.lstrip().startswith("{"):
        try:
            donnees = json.loads(texte)
        except (json.JSONDecodeError, ValueError):
            return texte
        if isinstance(donnees, dict) and isinstance(donnees.get("text"), str) and set(donnees) <= {"text", "images", "videos"}:
            return donnees["text"]
    return texte


def est_erreur(resultat):
    return isinstance(resultat, str) and resultat.startswith(_DEBUTS_ERREUR)
