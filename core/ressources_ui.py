"""Widgets MCP-UI : ressources `ui://` renvoyees par un outil MCP (chantier du 04/11/2026).

Avant : `_texte_depuis_blocs_mcp` (core/mcp_tools.py) reduisait tout bloc `resource` a la ligne
"[Ressource : ui://...]". Un serveur qui renvoie un widget (Higgsfield, par exemple) n'affichait
donc rien.

Maintenant, a cote du texte (qui reste le repli, inchange), on garde la structure du widget :
    {"uri", "mimeType", "genre": "html" | "url", "contenu", "donnees"?}
- genre "html" : `contenu` est le HTML, monte cote client dans une iframe `srcdoc` isolee.
- genre "url"  : `contenu` est une adresse http(s), montee dans une iframe `src`.
- les ressources d'un autre type (remote-dom, par exemple) ne sont pas rendues : le texte
  de repli reste seul.
Quand le serveur ne renvoie que l'adresse `ui://` sans contenu (cas des MCP Apps), le contenu est
lu au meme moment par `resources/read` sur la meme session.

Autre cas des MCP Apps (07/11/2026, Higgsfield `get_presets`) : le lien vers le widget est declare
sur la DEFINITION de l'outil (`_meta.ui.resourceUri`, renvoyee par tools/list) et le resultat ne
contient aucun bloc `ui://`. `adresse_widget_declaree` lit cette adresse sur l'outil, la route de
l'outil la garde (core/mcp_tools.py) et `collecter_ressources_ui` en lit le contenu par
`resources/read`. Un bloc `ui://` present dans le resultat reste prioritaire, et un resultat en
erreur n'affiche jamais le widget declare.

Le widget voyage dans une enveloppe JSON a cle unique, separee du texte AVANT toute troncature
(`_resultat_pour_affichage` coupe a 3000 caracteres) et avant l'envoi au modele :
`joindre_ressources_ui` cote outil MCP, `separer_ressources_ui` cote execution des outils.
Sans widget, le resultat n'est jamais modifie (aucune regression pour les autres outils).
"""
import asyncio
import base64
import json
import logging
import os

from core.plafonds_reglables import (
    DELAI_LECTURE_RESSOURCE_UI_SECONDES,
    PLAFOND_WIDGET_UI_OCTETS,
    PLAFOND_WIDGETS_UI_PAR_RESULTAT,
)

CLE_ENVELOPPE = "__classinus_ressources_ui"
_SCHEMA_UI = "ui://"
_FAUX = {"0", "false", "non", "off", "no"}


def ressources_ui_actives():
    """Interrupteur (variable CLASSINUS_MCP_UI_ACTIF, allume par defaut). Relu a chaque appel."""
    return os.environ.get("CLASSINUS_MCP_UI_ACTIF", "1").strip().lower() not in _FAUX


def _champ(objet, *noms):
    for nom in noms:
        valeur = getattr(objet, nom, None)
        if valeur:
            return valeur
    return None


def _texte_de_contenu(element):
    """Texte (HTML ou adresse) d'un objet de contenu MCP : `text`, sinon `blob` decode (base64)."""
    texte = getattr(element, "text", None)
    if isinstance(texte, str) and texte.strip():
        return texte
    blob = getattr(element, "blob", None)
    if isinstance(blob, str) and blob:
        try:
            return base64.b64decode(blob, validate=False).decode("utf-8")
        except Exception:
            logging.warning("Widget MCP-UI : contenu base64 illisible, ignore.")
    return None


def _premiere_adresse_http(texte):
    """Format text/uri-list (RFC 2483) : MCP-UI n'utilise que la premiere adresse http(s) valide."""
    for ligne in (texte or "").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and ligne.lower().startswith(("http://", "https://")):
            return ligne
    return None


def _genre(mime):
    mime = (mime or "").lower()
    if mime.startswith("text/html"):
        return "html"
    if mime.startswith("text/uri-list"):
        return "url"
    return None


def _candidats(blocs):
    """Ressources ui:// des blocs de contenu, brutes (contenu absent si le serveur n'a donne que l'uri)."""
    trouves = []
    for bloc in blocs or []:
        element = getattr(bloc, "resource", None) or bloc
        uri = getattr(element, "uri", None)
        if not isinstance(uri, str) or not uri.startswith(_SCHEMA_UI):
            continue
        mime = _champ(element, "mime_type", "mimeType") or ""
        trouves.append({"uri": uri, "mimeType": mime, "contenu": _texte_de_contenu(element)})
    return trouves


async def _lire_contenu_manquant(session, candidat):
    """resources/read sur la session de l'appel d'outil. Ne leve jamais : echec = pas de widget."""
    try:
        lu = await asyncio.wait_for(session.read_resource(candidat["uri"]), DELAI_LECTURE_RESSOURCE_UI_SECONDES)
    except Exception as e:
        logging.warning("Widget MCP-UI : lecture de %s impossible (%s).", candidat["uri"], type(e).__name__)
        return
    for contenu in getattr(lu, "contents", None) or []:
        texte = _texte_de_contenu(contenu)
        if texte:
            candidat["contenu"] = texte
            candidat["mimeType"] = _champ(contenu, "mime_type", "mimeType") or candidat["mimeType"]
            return


def _donnees_outil(resultat, texte):
    """Resultat de l'outil tel que le widget d'une MCP App l'attend (notification tool-result)."""
    donnees = {"content": [{"type": "text", "text": texte or ""}]}
    structure = getattr(resultat, "structured_content", None)
    if isinstance(structure, (dict, list)):
        donnees["structuredContent"] = structure
    return donnees


def adresse_widget_declaree(outil):
    """Adresse ui:// declaree par la DEFINITION d'un outil MCP (MCP Apps), sinon None. Ne leve jamais.

    Forme de la spec : `_meta.ui.resourceUri`, exposee par le SDK sous `outil.meta`. La cle plate
    `ui/resourceUri` est aussi acceptee. Toute valeur qui ne commence pas par ui:// est ignoree.
    """
    try:
        meta = getattr(outil, "meta", None)
        if not isinstance(meta, dict):
            return None
        ui = meta.get("ui")
        adresse = ui.get("resourceUri") if isinstance(ui, dict) else None
        if not adresse:
            adresse = meta.get("ui/resourceUri")
        if isinstance(adresse, str) and adresse.startswith(_SCHEMA_UI):
            return adresse
    except Exception:
        pass
    return None


async def collecter_ressources_ui(session, resultat, texte, adresse_declaree=None):
    """Widgets d'un resultat d'outil MCP, prets pour l'affichage. Liste vide si aucun, jamais d'exception.

    `adresse_declaree` : adresse ui:// lue sur la definition de l'outil (adresse_widget_declaree).
    Elle sert seulement quand le resultat n'a aucun bloc ui:// et n'est pas une erreur.
    """
    try:
        if not ressources_ui_actives():
            return []
        blocs = getattr(resultat, "content", None)
        candidats = _candidats(blocs)[:PLAFOND_WIDGETS_UI_PAR_RESULTAT]
        if (
            not candidats
            and isinstance(adresse_declaree, str)
            and adresse_declaree.startswith(_SCHEMA_UI)
            and not getattr(resultat, "is_error", False)
        ):
            logging.info("Widget MCP-UI %s : adresse declaree par la definition de l'outil.", adresse_declaree)
            candidats = [{"uri": adresse_declaree, "mimeType": "", "contenu": None}]
        for c in candidats:
            if not c["contenu"]:
                await _lire_contenu_manquant(session, c)
        finaux, vues = [], set()
        for c in candidats:
            genre = _genre(c["mimeType"])
            contenu = c["contenu"]
            if genre is None:
                logging.info("Widget MCP-UI %s : type %r non rendu, repli texte.", c["uri"], c["mimeType"])
                continue
            if genre == "url":
                contenu = _premiere_adresse_http(contenu)
            if not contenu or c["uri"] in vues:
                continue
            if len(contenu.encode("utf-8")) > PLAFOND_WIDGET_UI_OCTETS:
                logging.warning("Widget MCP-UI %s ignore : plus de %s octets.", c["uri"], PLAFOND_WIDGET_UI_OCTETS)
                continue
            vues.add(c["uri"])
            widget = {"uri": c["uri"], "mimeType": c["mimeType"], "genre": genre, "contenu": contenu}
            if genre == "html":
                widget["donnees"] = _donnees_outil(resultat, texte)
            finaux.append(widget)
        return finaux
    except Exception as e:
        logging.warning("Widgets MCP-UI ignores (%s) : le texte de repli est conserve.", e)
        return []


def joindre_ressources_ui(texte, ressources):
    """Enveloppe JSON {text, <cle>: [...]} si des widgets existent, sinon le texte inchange."""
    if not ressources:
        return texte
    try:
        donnees = json.loads(texte) if isinstance(texte, str) and texte.lstrip().startswith("{") else None
    except (json.JSONDecodeError, ValueError):
        donnees = None
    enveloppe = dict(donnees) if isinstance(donnees, dict) else {"text": texte or ""}
    enveloppe[CLE_ENVELOPPE] = ressources
    try:
        return json.dumps(enveloppe, ensure_ascii=False)
    except Exception:
        return texte


def separer_ressources_ui(resultat):
    """(resultat_sans_widget, widgets). Resultat sans widget : renvoye tel quel avec une liste vide."""
    if not isinstance(resultat, str) or CLE_ENVELOPPE not in resultat:
        return resultat, []
    try:
        donnees = json.loads(resultat)
    except (json.JSONDecodeError, ValueError):
        return resultat, []
    if not isinstance(donnees, dict) or not isinstance(donnees.get(CLE_ENVELOPPE), list):
        return resultat, []
    widgets = donnees.pop(CLE_ENVELOPPE)
    if set(donnees) <= {"text"}:
        return donnees.get("text", ""), widgets
    return json.dumps(donnees, ensure_ascii=False), widgets


NOTE_POUR_LE_MODELE = (
    "[Un widget interactif est déjà affiché à l'utilisateur dans la conversation : ne recopie pas "
    "l'adresse ui:// dans ta réponse, décris-le juste brièvement en texte si besoin.]"
)
