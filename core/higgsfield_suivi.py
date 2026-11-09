"""Suivi serveur des générations Higgsfield (page /higgsfield).

Chaque génération lancée est enregistrée dans higgsfield_generations. Une boucle
de fond (voir api/main.py) interroge Higgsfield, sauvegarde le résultat en
bibliothèque et envoie la notification, même si l'application est fermée.
L'état vit en base : un redémarrage du serveur ne perd rien.
"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from api.auth import supabase
from core.bibliotheque_fichiers import enregistrer_fichier
from core.generation_video_higgsfield import statut_generation
from core.higgsfield_marketing_studio import PREFIXE_SUIVI, lire_statut as lire_statut_marketing
from core.notifications import creer_notification
from core.notifications_push import envoyer_notification_push

TABLE = "higgsfield_generations"
# Au-delà, une génération toujours en cours est déclarée en échec (Higgsfield ne répond plus).
DELAI_MAX = timedelta(hours=2)
LOT_MAX = 50
_EXTENSIONS_IMAGE = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def enregistrer(user_id: str, request_id: str, titre: str, genre: str) -> None:
    """Appelé juste après le lancement. Ne lève jamais : la génération est déjà partie chez Higgsfield."""
    try:
        supabase.table(TABLE).insert(
            {"user_id": user_id, "request_id": request_id, "titre": titre.strip() or f"Higgsfield_{request_id}", "genre": genre}
        ).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (enregistrement generation Higgsfield {request_id}, user {user_id}) : {e}")


def lister(user_id: str, limite: int = 20) -> list[dict]:
    res = (
        supabase.table(TABLE)
        .select("request_id,titre,genre,etat,etape,url,erreur,sauvegardee,partage_termine_a,cree_a,termine_a")
        .eq("user_id", user_id)
        .order("cree_a", desc=True)
        .limit(max(1, min(limite, 50)))
        .execute()
    )
    return res.data or []


def obtenir(user_id: str, request_id: str) -> dict | None:
    res = (
        supabase.table(TABLE)
        .select("request_id,titre,genre,etat,etape,url,erreur,sauvegardee,partage_termine_a,cree_a,termine_a")
        .eq("user_id", user_id)
        .eq("request_id", request_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def marquer_annulee(user_id: str, request_id: str) -> None:
    supabase.table(TABLE).update({"etat": "annulee", "termine_a": _maintenant()}).eq("user_id", user_id).eq(
        "request_id", request_id
    ).eq("etat", "en_cours").execute()


def _revendiquer(request_id: str, colonne: str) -> bool:
    """Prend le droit d'effectuer une action une seule fois (sauvegarde ou notification), même
    si deux traitements tournent en même temps : seul celui dont la mise à jour modifie la ligne continue."""
    res = supabase.table(TABLE).update({colonne: True}).eq("request_id", request_id).eq(colonne, False).execute()
    return bool(res.data)


def _rendre(request_id: str, colonne: str) -> None:
    try:
        supabase.table(TABLE).update({colonne: False}).eq("request_id", request_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (reprise {colonne} Higgsfield {request_id}) : {e}")


def _sauvegarder(ligne: dict, url: str) -> bool:
    """Télécharge le résultat et l'ajoute à la bibliothèque de l'utilisateur. True si réussi."""
    nom = ligne["titre"]
    extension = url.split("?")[0].rsplit(".", 1)[-1].lower()
    if extension in _EXTENSIONS_IMAGE:
        nom_fichier, mime = f"{nom}.{extension}", _EXTENSIONS_IMAGE[extension]
    elif ligne["genre"] == "image":
        nom_fichier, mime = f"{nom}.png", "image/png"
    else:
        nom_fichier, mime = f"{nom}.mp4", "video/mp4"
    try:
        reponse = requests.get(url, timeout=60)
        reponse.raise_for_status()
        enregistrer_fichier(
            contenu=reponse.content,
            nom_fichier=nom_fichier,
            type_mime=mime,
            niveau="utilisateur",
            uploade_par=ligne["user_id"],
            user_id=ligne["user_id"],
            description=nom_fichier,
            origine="ia_generee",
        )
        return True
    except Exception as e:
        logging.error(f"ERREUR sauvegarde bibliotheque Higgsfield {ligne['request_id']} : {e}")
        return False


def _notifier(ligne: dict, etat: str) -> None:
    if not _revendiquer(ligne["request_id"], "notifiee"):
        return
    if etat == "terminee":
        titre, corps = "Ta génération est prête", f"« {ligne['titre']} » est enregistrée dans ta bibliothèque."
        titre_en, corps_en = "Your generation is ready", f"“{ligne['titre']}” is saved in your library."
    else:
        titre, corps = "Ta génération n'a pas abouti", f"« {ligne['titre']} » n'a pas pu être terminée."
        titre_en, corps_en = "Your generation did not complete", f"“{ligne['titre']}” could not be completed."
    try:
        # Dans l'appli, le texte français est traduit par le dictionnaire de l'interface (lib/i18n/interface.ts).
        creer_notification(ligne["user_id"], "action_ia_terminee", titre, corps, "/higgsfield")
        # Sur l'appareil, la langue de l'utilisateur n'est pas connue du serveur : les deux langues sont envoyees.
        envoyer_notification_push(
            ligne["user_id"], f"{titre} · {titre_en}", f"{corps}\n{corps_en}", "/higgsfield"
        )
    except Exception as e:
        logging.error(f"ERREUR notification Higgsfield {ligne['request_id']} : {e}")


def _terminer(ligne: dict, etat: str, url: str | None, erreur: str | None) -> None:
    supabase.table(TABLE).update({"etat": etat, "url": url, "erreur": erreur, "termine_a": _maintenant()}).eq(
        "request_id", ligne["request_id"]
    ).execute()


def _traiter_une(ligne: dict) -> None:
    request_id = ligne["request_id"]
    cree = datetime.fromisoformat(ligne["cree_a"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - cree > DELAI_MAX:
        _terminer(ligne, "echec", None, "delai_depasse")
        _notifier(ligne, "echec")
        return
    try:
        if request_id.startswith(PREFIXE_SUIVI):
            # Generation Marketing Studio lancee par le compte partage (MCP), pas par l'API.
            resultat = lire_statut_marketing(request_id[len(PREFIXE_SUIVI):])
        else:
            resultat = statut_generation(request_id)
    except Exception as e:
        # Panne passagère de Higgsfield : on réessaie au prochain tour.
        logging.warning(f"Suivi Higgsfield {request_id} : statut indisponible ({e})")
        return
    etat = resultat["etat"]
    if etat == "en_cours":
        # L'étape (en attente de son tour / création en cours) est remontée à l'appli.
        supabase.table(TABLE).update({"verifie_a": _maintenant(), "etape": resultat.get("etape", "creation")}).eq(
            "request_id", request_id
        ).execute()
        return
    if etat == "terminee":
        url = resultat.get("url")
        if not url:
            return
        if _revendiquer(request_id, "sauvegardee"):
            if not _sauvegarder(ligne, url):
                _rendre(request_id, "sauvegardee")  # réessayé au prochain tour
                return
        _terminer(ligne, "terminee", url, None)
        _notifier(ligne, "terminee")
        return
    _terminer(ligne, etat, None, resultat.get("erreur"))
    _notifier(ligne, etat)


def traiter_en_cours() -> int:
    """Un tour de suivi : renvoie le nombre de générations examinées. Appelé par la boucle de fond."""
    res = (
        supabase.table(TABLE)
        .select("request_id,user_id,titre,genre,cree_a")
        .eq("etat", "en_cours")
        .order("cree_a")
        .limit(LOT_MAX)
        .execute()
    )
    lignes = res.data or []
    for ligne in lignes:
        try:
            _traiter_une(ligne)
        except Exception as e:
            logging.error(f"ERREUR suivi Higgsfield {ligne.get('request_id')} : {e}")
    return len(lignes)


def traiter_une_generation(user_id: str, request_id: str) -> None:
    """Rafraîchit tout de suite une génération de l'utilisateur (appelé quand l'appli la regarde)."""
    res = (
        supabase.table(TABLE)
        .select("request_id,user_id,titre,genre,cree_a")
        .eq("user_id", user_id)
        .eq("request_id", request_id)
        .eq("etat", "en_cours")
        .limit(1)
        .execute()
    )
    if res.data:
        _traiter_une(res.data[0])
