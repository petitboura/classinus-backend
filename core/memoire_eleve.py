"""
Mémoire élève persistante et incrémentale (chantier 27/09/2026, demande
Bourama). C'est l'unique système de mémoire de l'élève : l'ancien
système (résumé automatique et outil gerer_memoire_utilisateur, table
conversation_summaries) a été retiré.

L'ancien système stockait tout dans un unique JSON par élève, fusion
au premier niveau seulement (dict.update) : une mise à jour sur une clé
de premier niveau déjà utilisée écrasait tout son contenu imbriqué au
lieu de le compléter, symptôme rapporté par Bourama d'une mémoire qui
"change" au lieu de s'accumuler. Nouveau principe ici : une ligne par
(élève, catégorie, sous_categorie) dans memoire_eleve (voir
migrations/2026_09_27_memoire_eleve.sql), jamais de réécriture globale ,
une écriture ne touche jamais que sa propre ligne.

Aucune catégorie imposée (décision de Bourama, 29/10/2026) : le modèle
crée et structure lui-même autant de grandes catégories et de
sous-catégories qu'il veut, à tout moment (pendant un tour, un message,
une conversation). Il doit privilégier quelques grandes catégories
avec des sous-catégories plutôt que des dizaines de catégories à plat.
Les noms sont seulement normalisés (minuscules, sans accents, sans
espaces) pour éviter les doublons du type "Scolarité" / "scolarite".

Ce module ne connaît rien du protocole MCP (voir
core/outils_memoire_eleve.py pour les outils appelés par le modèle) ,
seulement l'accès Supabase, même découpage que
core/historique_reponses_qcm.py / core/outils_reponses_qcm.py.
"""

import logging
import re
import unicodedata
from datetime import datetime, timezone

from core.outils_generation_commun import _supabase_memoire

LONGUEUR_MAX_NOM = 80


def normaliser_nom(nom: str | None) -> str:
    """
    Normalise un nom de catégorie ou de sous-catégorie : minuscules, sans
    accents, espaces et séparateurs remplacés par un tiret bas, seuls
    a-z 0-9 _ - . conservés (le point sépare les niveaux d'une
    sous-catégorie). Chaîne vide si rien d'exploitable.
    """
    if not nom:
        return ""
    sans_accents = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode("ascii")
    propre = re.sub(r"[^a-z0-9_.\-]+", "_", sans_accents.lower().strip())
    propre = re.sub(r"_+", "_", propre).strip("_.")
    return propre[:LONGUEUR_MAX_NOM]

_TABLE = "memoire_eleve"

# Chaîne vide, jamais NULL, pour représenter "pas de sous-catégorie"
# (ligne racine d'une catégorie) : deux NULL ne sont jamais égaux pour une
# contrainte unique Postgres, ce qui casserait à la fois l'unicité
# (user_id, categorie, sous_categorie) et l'upsert on_conflict ci-dessous
# si on utilisait NULL. Converti en None uniquement à la sortie vers
# l'appelant (voir _vers_api/_depuis_api).
_RACINE = ""


def _depuis_api(sous_categorie: str | None) -> str:
    return sous_categorie if sous_categorie else _RACINE


def _vers_api(sous_categorie: str) -> str | None:
    return sous_categorie or None


def obtenir_sommaire(user_id: str) -> list[dict]:
    """
    Une entrée par catégorie/sous-catégorie déjà connue pour cet élève :
    categorie, sous_categorie, description, updated_at, JAMAIS le
    contenu (voir lire_categorie pour ça, à n'appeler que sur la ligne
    précise identifiée ici). Aucune catégorie n'est ajoutée d'office : le sommaire
    reflète uniquement ce que le modèle a lui-même créé.
    Liste vide en cas d'erreur Supabase, jamais d'exception vers
    l'appelant (même convention que historique_reponses_qcm.py).
    """
    try:
        lignes = (
            _supabase_memoire.table(_TABLE)
            .select("categorie, sous_categorie, description, updated_at")
            .eq("user_id", user_id)
            .execute()
        ).data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (sommaire memoire_eleve, user {user_id}) : {e}")
        return []

    for ligne in lignes:
        ligne["sous_categorie"] = _vers_api(ligne["sous_categorie"])

    lignes.sort(key=lambda l: (l["categorie"], l["sous_categorie"] or ""))
    return lignes


def formater_sommaire(lignes: list[dict]) -> str:
    """
    Texte du sommaire, une ligne par catégorie ou sous-catégorie :
    "chemin: description (maj: date)" ou "chemin: (vide)". Format unique,
    partagé par l'outil memoire_sommaire et par l'envoi automatique du
    sommaire au chat et à la voix, pour que le modèle voie toujours la
    même chose.
    """
    textes = []
    for l in lignes:
        chemin = l["categorie"] if not l["sous_categorie"] else f"{l['categorie']}.{l['sous_categorie']}"
        if not l.get("description"):
            textes.append(f"{chemin}: (sans résumé)")
        else:
            textes.append(f"{chemin}: {l['description']} (maj: {l['updated_at']})")
    return "\n".join(textes)


def construire_bloc_sommaire(lignes: list[dict] | None, pour_voix: bool = False) -> str:
    """
    Bloc de prompt donné d'office au modèle : le sommaire de la mémoire de
    l'élève, déjà lu. Chaîne vide si on n'a pas pu le lire. Le contenu
    détaillé n'est jamais inclus ici, seulement les titres et résumés.

    pour_voix=False : texte du chat, qui peut appeler memoire_lire.
    pour_voix=True : texte de la voix Gemini Live, qui n'a aucun outil
    mémoire et ne fait que transmettre les demandes à Classinus.
    """
    if not lignes:
        return ""
    if pour_voix:
        intro = (
            "\n\nSOMMAIRE DE LA MÉMOIRE DE L'ÉTUDIANT (déjà lu). Une ligne par sujet : titre, résumé, "
            "date de dernière mise à jour. Voici comment t'en servir :\n"
            "1. Appelle l'étudiant par son prénom, tel qu'il apparaît dans le sommaire, souvent et "
            "naturellement, sans en faire trop.\n"
            "2. Si le sommaire indique comment l'étudiant appelle Classinus (un surnom), ce surnom est "
            "aussi ton nom : quand l'étudiant le prononce, c'est à toi qu'il s'adresse, exactement comme "
            "s'il disait Classinus.\n"
            "3. Respecte ses préférences d'expression indiquées dans le sommaire (ton, genre grammatical "
            "avec lequel tu parles de toi).\n"
            "4. Ne lis jamais le sommaire à voix haute et n'annonce jamais que tu consultes sa mémoire. "
            "Pour toute vraie demande, tu passes toujours par Classinus comme d'habitude.\n"
        )
    else:
        intro = (
            "\n\nSOMMAIRE DE LA MÉMOIRE DE CET ÉLÈVE (déjà lu, tu n'as pas besoin de l'outil "
            "memoire_sommaire pour le consulter). Une ligne par sujet : titre, résumé, date de "
            "dernière mise à jour. Ce sont seulement des résumés, pas le détail :\n"
        )
    return intro + formater_sommaire(lignes)


def lire_categorie(user_id: str, categorie: str, sous_categorie: str | None = None) -> dict | None:
    """
    Contenu complet d'UNE seule ligne (categorie/sous_categorie) pour cet
    élève. None si elle n'existe pas encore, ou en cas d'erreur Supabase
    (jamais d'exception vers l'appelant).
    """
    try:
        res = (
            _supabase_memoire.table(_TABLE)
            .select("contenu, description, updated_at")
            .eq("user_id", user_id)
            .eq("categorie", normaliser_nom(categorie))
            .eq("sous_categorie", _depuis_api(normaliser_nom(sous_categorie)))
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture memoire_eleve, user {user_id}, {categorie}/{sous_categorie}) : {e}")
        return None
    # maybe_single().execute() renvoie None (pas un objet vide) quand la ligne
    # n'existe pas, comme partout ailleurs dans le depot : tester res avant res.data.
    if not res or not res.data:
        return None
    return res.data


def ecrire_categorie(
    user_id: str,
    categorie: str,
    sous_categorie: str | None,
    contenu: dict,
    description: str,
) -> tuple[bool, str | None]:
    """
    Crée ou remplace le contenu d'UNE SEULE ligne (categorie/sous_categorie),
    jamais les autres lignes de cet élève, c'est tout le principe de
    cette refonte (voir docstring de module). `categorie` est libre
    (créée à la volée si elle n'existe pas), seulement normalisée.

    Renvoie (succes, message_erreur). message_erreur est None en cas de
    succès, sinon un texte prêt à être renvoyé tel quel par l'outil MCP
    appelant.
    """
    categorie = normaliser_nom(categorie)
    sous_categorie = normaliser_nom(sous_categorie) or None
    if not categorie:
        return False, "Erreur : nom de catégorie manquant ou invalide."
    ligne = {
        "user_id": user_id,
        "categorie": categorie,
        "sous_categorie": _depuis_api(sous_categorie),
        "contenu": contenu,
        "description": description,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _supabase_memoire.table(_TABLE).upsert(
            ligne, on_conflict="user_id,categorie,sous_categorie"
        ).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (écriture memoire_eleve, user {user_id}, {categorie}/{sous_categorie}) : {e}")
        return False, "Erreur : l'écriture en mémoire a échoué, réessaie."
    return True, None


def _fusion_profonde(existant: dict, ajouts: dict) -> dict:
    """
    Fusion qui ne perd jamais rien : un dict est fusionné clé par clé
    (récursivement), une liste reçoit les éléments qu'elle n'a pas déjà,
    toute autre valeur est remplacée par la nouvelle.
    """
    resultat = dict(existant)
    for cle, valeur in ajouts.items():
        ancien = resultat.get(cle)
        if isinstance(ancien, dict) and isinstance(valeur, dict):
            resultat[cle] = _fusion_profonde(ancien, valeur)
        elif isinstance(ancien, list) and isinstance(valeur, list):
            resultat[cle] = ancien + [v for v in valeur if v not in ancien]
        else:
            resultat[cle] = valeur
    return resultat


def completer_categorie(
    user_id: str,
    categorie: str,
    sous_categorie: str | None,
    ajouts: dict,
    description: str,
) -> tuple[bool, str | None]:
    """
    Ajoute ou modifie seulement quelques éléments d'UNE ligne sans jamais
    renvoyer ni réécrire le reste de son contenu (chantier du 26/10/2026,
    demande de Bourama : écrire sans tout relire ni tout réécrire).
    La lecture ici est stricte : en cas d'erreur Supabase on s'arrête,
    on n'écrit JAMAIS à partir d'un contenu qu'on n'a pas pu lire, sinon
    une panne de lecture effacerait la fiche existante.
    """
    categorie = normaliser_nom(categorie)
    sous = normaliser_nom(sous_categorie)
    if not categorie:
        return False, "Erreur : nom de catégorie manquant ou invalide."
    try:
        res = (
            _supabase_memoire.table(_TABLE)
            .select("contenu")
            .eq("user_id", user_id)
            .eq("categorie", categorie)
            .eq("sous_categorie", _depuis_api(sous))
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture avant ajout memoire_eleve, user {user_id}, {categorie}/{sous}) : {e}")
        return False, "Erreur : impossible de lire cette catégorie avant d'y ajouter, réessaie."
    lignes = (res.data if res else None) or []
    existant = (lignes[0].get("contenu") or {}) if lignes else {}
    return ecrire_categorie(user_id, categorie, sous or None, _fusion_profonde(existant, ajouts), description)
