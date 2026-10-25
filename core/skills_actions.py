"""Actions de l'outil gerer_skill : l'IA lit, crée et modifie les skills d'un utilisateur.

Aucune règle n'est recopiée ici : tout passe par les fonctions de api/skills.py
(validation des chemins, plafonds de taille, en-tête du SKILL.md qui suit le Nom et la
Description, envoi tout ou rien vers R2). L'IA et l'éditeur obéissent donc aux mêmes règles.
Ce module ne dépend pas du serveur MCP, pour pouvoir être testé seul.
"""
import logging
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from api import skills as _api
from core import config_skills
from core.skills_entete import lire_entete

ACTIONS = (
    "lister", "consulter", "creer", "modifier_infos", "ecrire_fichier",
    "remplacer_texte", "supprimer_fichier", "supprimer",
)


class _Refus(Exception):
    """Refus clair, destiné à l'IA (jamais une erreur technique)."""


def _message_http(e: HTTPException) -> str:
    detail = e.detail
    if isinstance(detail, dict):
        return detail.get("message") or "Opération impossible."
    return str(detail)


def _chemin_valide(chemin: str) -> str:
    if not (chemin or "").strip():
        raise _Refus("Il faut préciser le chemin du fichier (par exemple references/guide.md).")
    return _api._path(chemin)


def _charger_complet(skill_id: str, user_id: str) -> tuple[dict, dict[str, str]]:
    """Charge le skill et tous ses fichiers texte. Refuse s'il contient un fichier non texte.

    Une modification réécrit tout le skill : un fichier non texte serait effacé sans
    prévenir. On refuse donc plutôt que de risquer de le perdre.
    """
    ligne = _api._owned(skill_id, user_id)
    fichiers: dict[str, str] = {}
    for item in _api._files(skill_id, True):
        if item.get("binaire"):
            raise _Refus(
                f"Le fichier {item['chemin']} n'est pas du texte : le modifier depuis le chat "
                "l'effacerait. Aucune modification n'a été faite."
            )
        fichiers[item["chemin"]] = item["contenu"]
    return ligne, fichiers


def _enregistrer(skill_id: str, user_id: str, ligne: dict, fichiers: dict[str, str], nom: str, description: str, actif: bool) -> None:
    payload = _api.SkillPayload(
        nom=nom, description=description, actif=actif,
        fichiers=[_api.Fichier(chemin=c, contenu=t) for c, t in fichiers.items()],
    )
    _api.modifier(skill_id, payload, SimpleNamespace(id=user_id))


def _tronquer(texte: str) -> str:
    maximum = config_skills.LECTURE_CARACTERES_MAX
    if len(texte) <= maximum:
        return texte
    return texte[:maximum] + f"\n\n[Lecture coupée après {maximum} caractères sur {len(texte)}.]"


def _booleen(valeur: str) -> bool | None:
    v = (valeur or "").strip().lower()
    if v in ("oui", "true", "1", "actif", "active", "activer"):
        return True
    if v in ("non", "false", "0", "inactif", "desactive", "desactiver"):
        return False
    if v == "":
        return None
    raise _Refus('Le paramètre actif doit valoir "oui" ou "non".')


def _lister(user_id: str) -> str:
    rows = (
        _api.supabase.table("skills").select("id,nom,description,actif,updated_at")
        .eq("owner_id", user_id).order("updated_at", desc=True).execute().data or []
    )
    if not rows:
        return "Aucun skill pour l'instant."
    lignes = []
    for r in rows:
        etat = "actif" if r.get("actif", True) else "désactivé"
        lignes.append(f"- {r.get('nom')} ({etat}) : {r.get('description') or '(sans description)'}\n  [id interne, ne jamais montrer à l'utilisateur : {r['id']}]")
    return "\n".join(lignes)


def _consulter(user_id: str, skill_id: str, chemin: str) -> str:
    ligne = _api._owned(skill_id, user_id)
    rows = _api.supabase.table("skill_files").select("*").eq("skill_id", skill_id).order("chemin").execute().data or []
    cible = _chemin_valide(chemin) if (chemin or "").strip() else "SKILL.md"
    row = next((r for r in rows if r["chemin"] == cible), None)
    if row is None:
        disponibles = ", ".join(r["chemin"] for r in rows) or "aucun"
        raise _Refus(f"Le fichier {cible} n'existe pas dans ce skill. Fichiers disponibles : {disponibles}.")
    item = _api._lire(row)
    if item.get("binaire"):
        return f"Le fichier {cible} n'est pas du texte, son contenu ne peut pas être lu ici."
    etat = "actif" if ligne.get("actif", True) else "désactivé"
    sortie = f"Skill : {ligne['nom']} ({etat})\nFichier : {cible}\n\n{_tronquer(item['contenu'])}"
    autres = [r for r in rows if r["chemin"] != cible]
    if cible == "SKILL.md" and autres:
        sortie += "\n\nAutres fichiers de ce skill (à lire seulement si le SKILL.md le demande) :\n" + "\n".join(
            f"- {r['chemin']} ({r.get('taille_octets', 0)} octets)" for r in autres
        )
    return sortie


def _creer(user_id: str, nom: str, description: str, contenu: str) -> str:
    if not (nom or "").strip():
        raise _Refus("Il faut un nom pour créer un skill.")
    fichiers = [_api.Fichier(chemin="SKILL.md", contenu=contenu)] if (contenu or "").strip() else []
    payload = _api.SkillPayload(nom=nom, description=description or "", actif=True, fichiers=fichiers)
    cree = _api._creer_skill(payload, SimpleNamespace(id=user_id))
    return (
        f"Skill créé : {cree['nom']} (id {cree['id']}). Le SKILL.md est enregistré avec un en-tête "
        "qui reprend le nom et la description. Pour ajouter d'autres fichiers (scripts/, references/, "
        "assets/), utilise l'action ecrire_fichier."
    )


def _modifier_infos(user_id: str, skill_id: str, nom: str, description: str, actif: str) -> str:
    nouvel_actif = _booleen(actif)
    if not (nom or "").strip() and not (description or "").strip() and nouvel_actif is None:
        raise _Refus("Indique au moins une chose à changer : nom, description ou actif.")
    ligne, fichiers = _charger_complet(skill_id, user_id)
    nom_final = (nom or "").strip() or ligne["nom"]
    description_finale = (description or "").strip() or ligne.get("description") or ""
    actif_final = ligne.get("actif", True) if nouvel_actif is None else nouvel_actif
    _enregistrer(skill_id, user_id, ligne, fichiers, nom_final, description_finale, actif_final)
    return f"Skill mis à jour : {nom_final} ({'actif' if actif_final else 'désactivé'}). L'en-tête du SKILL.md a suivi."


def _note_entete(chemin: str, contenu: str, ligne: dict) -> str:
    if chemin != "SKILL.md":
        return ""
    entete = lire_entete(contenu)
    if (entete.get("name") or ligne["nom"]) != ligne["nom"] or (entete.get("description") or ligne.get("description") or "") != (ligne.get("description") or ""):
        return (
            " Attention : l'en-tête du SKILL.md est toujours remis à jour avec le nom et la description du skill. "
            "Pour les changer, utilise l'action modifier_infos."
        )
    return ""


def _ecrire_fichier(user_id: str, skill_id: str, chemin: str, contenu: str) -> str:
    cible = _chemin_valide(chemin)
    ligne, fichiers = _charger_complet(skill_id, user_id)
    existait = cible in fichiers
    fichiers[cible] = contenu or ""
    _enregistrer(skill_id, user_id, ligne, fichiers, ligne["nom"], ligne.get("description") or "", ligne.get("actif", True))
    return f"Fichier {cible} {'remplacé' if existait else 'créé'} dans le skill {ligne['nom']}." + _note_entete(cible, contenu or "", ligne)


def _remplacer_texte(user_id: str, skill_id: str, chemin: str, ancien: str, nouveau: str) -> str:
    cible = _chemin_valide(chemin)
    if not ancien:
        raise _Refus("Il faut préciser le texte à remplacer (paramètre ancien).")
    ligne, fichiers = _charger_complet(skill_id, user_id)
    if cible not in fichiers:
        raise _Refus(f"Le fichier {cible} n'existe pas dans ce skill. Fichiers disponibles : {', '.join(fichiers) or 'aucun'}.")
    occurrences = fichiers[cible].count(ancien)
    if occurrences == 0:
        raise _Refus("Ce texte est introuvable dans le fichier. Relis le fichier avec consulter et recopie le passage exactement.")
    if occurrences > 1:
        raise _Refus(f"Ce texte apparaît {occurrences} fois dans le fichier. Ajoute du texte autour pour qu'il soit unique.")
    fichiers[cible] = fichiers[cible].replace(ancien, nouveau or "", 1)
    _enregistrer(skill_id, user_id, ligne, fichiers, ligne["nom"], ligne.get("description") or "", ligne.get("actif", True))
    return f"Texte remplacé dans {cible}." + _note_entete(cible, fichiers[cible], ligne)


def _supprimer_fichier(user_id: str, skill_id: str, chemin: str) -> str:
    cible = _chemin_valide(chemin)
    if cible == "SKILL.md":
        raise _Refus("Le SKILL.md ne peut pas être supprimé : c'est le fichier principal du skill.")
    ligne, fichiers = _charger_complet(skill_id, user_id)
    if cible not in fichiers:
        raise _Refus(f"Le fichier {cible} n'existe pas dans ce skill. Fichiers disponibles : {', '.join(fichiers) or 'aucun'}.")
    del fichiers[cible]
    _enregistrer(skill_id, user_id, ligne, fichiers, ligne["nom"], ligne.get("description") or "", ligne.get("actif", True))
    return f"Fichier {cible} supprimé du skill {ligne['nom']}."


def _supprimer(user_id: str, skill_id: str) -> str:
    ligne = _api._owned(skill_id, user_id)
    _api.supprimer(skill_id, SimpleNamespace(id=user_id))
    return f"Skill supprimé : {ligne['nom']}."


def executer(
    user_id: str, action: str, skill_id: str = "", nom: str = "", description: str = "",
    contenu: str = "", chemin: str = "", ancien: str = "", nouveau: str = "", actif: str = "",
) -> str:
    """Exécute une action et renvoie toujours un texte pour l'IA (jamais une exception)."""
    action = (action or "").strip().lower()
    try:
        if action not in ACTIONS:
            return f"Erreur : action \"{action}\" inconnue. Actions valides : {', '.join(ACTIONS)}."
        if action == "lister":
            return _lister(user_id)
        if action == "creer":
            return _creer(user_id, nom, description, contenu)
        if not (skill_id or "").strip():
            return "Erreur : il faut préciser le skill (paramètre skill_id). Utilise l'action lister pour le retrouver."
        if action == "consulter":
            return _consulter(user_id, skill_id, chemin)
        if action == "modifier_infos":
            return _modifier_infos(user_id, skill_id, nom, description, actif)
        if action == "ecrire_fichier":
            return _ecrire_fichier(user_id, skill_id, chemin, contenu)
        if action == "remplacer_texte":
            return _remplacer_texte(user_id, skill_id, chemin, ancien, nouveau)
        if action == "supprimer_fichier":
            return _supprimer_fichier(user_id, skill_id, chemin)
        return _supprimer(user_id, skill_id)
    except _Refus as e:
        return f"Erreur : {e}"
    except HTTPException as e:
        return f"Erreur : {_message_http(e)}"
    except ValidationError:
        return "Erreur : une limite du skill est dépassée (taille d'un fichier, nombre de fichiers ou longueur du nom ou de la description)."
    except Exception as e:
        logging.error(f"ERREUR gerer_skill ({action}) : {e}")
        return "Erreur : l'opération sur le skill a échoué, réessaie."
