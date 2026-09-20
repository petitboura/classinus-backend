"""
Minuteurs dans le chat (20/09/2026, demande Bourama) : un minuteur qui ne
bloque rien, que l'etudiant OU Clovis peut lancer, que l'on peut arreter
ou modifier, et sur lequel Clovis agit quand il se termine.

Toute la logique vit ici, pour que les deux facons de s'en servir (l'outil
de Clovis, core/outils_minuteurs.py, et les boutons de l'etudiant,
api/minuteurs.py) passent par exactement les memes regles.

Principe : la fin d'un minuteur est un INSTANT ABSOLU enregistre en base
(fin_prevue), pas un compteur qui descend dans une page. Le minuteur
survit donc a un changement de page, a la fermeture de l'appli et a une
ouverture sur un autre appareil, et arreter/modifier ne fait que changer
cette ligne (voir migrations/2026_09_20_minuteurs.sql).

Fin d'un minuteur : l'appli ouverte "prend en charge" la fin (route
/terminer, voir api/minuteurs.py). Cette prise en charge est ATOMIQUE :
meme si l'appli est ouverte sur trois appareils, un seul obtient
a_traiter=True, donc Clovis n'est reveille qu'une fois. Si personne n'a
pris en charge la fin apres DELAI_AVANT_NOTIFICATION_SECONDES (appli
fermee), le planificateur envoie une notification, et la fin sera prise
en charge a la prochaine ouverture de l'appli.
"""

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone

from api.auth import supabase

# Garde-fous LARGES, pas des limites produit tranchees avec Bourama
# (a valider avec lui). Regroupes ici pour qu'ils soient faciles a
# changer sans toucher au reste du code.
DUREE_MIN_SECONDES = 10
DUREE_MAX_SECONDES = 12 * 3600
NB_MAX_MINUTEURS_ACTIFS = 5
LONGUEUR_MAX_TITRE = 80
LONGUEUR_MAX_ACTION_FIN = 500

# Marge acceptee entre l'horloge de l'appareil de l'etudiant et celle du
# serveur quand l'appli signale qu'un minuteur est arrive a zero.
TOLERANCE_FIN_SECONDES = 3

# Laisse a l'appli ouverte le temps de prendre en charge la fin avant
# d'envoyer une notification : sans ce delai, un minuteur fini sous les
# yeux de l'etudiant declencherait aussi une notification inutile.
DELAI_AVANT_NOTIFICATION_SECONDES = 20


class ErreurMinuteur(Exception):
    """Erreur metier portant un code stable de core/erreurs.py (traduit
    cote frontend) et le statut HTTP a utiliser si elle sort par une
    route. L'outil de Clovis, lui, lit `code` pour repondre en francais
    au modele."""

    def __init__(self, code: str, statut_http: int = 400):
        super().__init__(code)
        self.code = code
        self.statut_http = statut_http


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _lire_date(valeur: str) -> datetime:
    return datetime.fromisoformat(valeur)


def _nettoyer_texte(valeur, longueur_max: int) -> str | None:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte[:longueur_max] if texte else None


def serialiser(ligne: dict, maintenant: datetime | None = None) -> dict:
    """Forme unique renvoyee au frontend et a Clovis. Le temps restant est
    calcule ici, avec l'horloge du serveur, jamais devine par l'appli."""
    maintenant = maintenant or _maintenant()
    # Arrondi au dessus : un minuteur de 5 minutes qui vient d'etre lance
    # doit indiquer 5 min, pas 4 min 59 s.
    restant = math.ceil((_lire_date(ligne["fin_prevue"]) - maintenant).total_seconds())
    return {
        "id": ligne["id"],
        "titre": ligne.get("titre"),
        "duree_secondes": ligne["duree_secondes"],
        "fin_prevue": ligne["fin_prevue"],
        "secondes_restantes": max(0, restant),
        "statut": ligne["statut"],
        "action_fin": ligne.get("action_fin"),
        "lance_par": ligne["lance_par"],
        "conversation_id": ligne.get("conversation_id"),
    }


def _lire_ligne(user_id: str, minuteur_id: str) -> dict | None:
    try:
        uuid.UUID(str(minuteur_id))
    except ValueError:
        return None
    try:
        res = (
            supabase.table("minuteurs")
            .select("*")
            .eq("id", minuteur_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture minuteur {minuteur_id}) : {e}")
        raise ErreurMinuteur("MINUTEUR_ECHEC", 500)
    return res.data if res is not None and res.data else None


def lister_minuteurs_actifs(user_id: str) -> list[dict]:
    """Minuteurs en cours de l'etudiant, le plus proche de sa fin en
    premier. Inclut ceux dont la fin est deja passee mais que personne
    n'a encore pris en charge (statut toujours 'en_cours')."""
    try:
        res = (
            supabase.table("minuteurs")
            .select("*")
            .eq("user_id", user_id)
            .eq("statut", "en_cours")
            .order("fin_prevue")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (liste minuteurs user={user_id}) : {e}")
        raise ErreurMinuteur("MINUTEUR_ECHEC", 500)
    return res.data or []


def creer_minuteur(
    user_id: str,
    duree_secondes: int,
    titre: str | None = None,
    action_fin: str | None = None,
    lance_par: str = "clovis",
    conversation_id: str | None = None,
) -> dict:
    if lance_par not in ("clovis", "etudiant"):
        raise ErreurMinuteur("REQUETE_INVALIDE")
    if (
        not isinstance(duree_secondes, int)
        or isinstance(duree_secondes, bool)
        or not (DUREE_MIN_SECONDES <= duree_secondes <= DUREE_MAX_SECONDES)
    ):
        raise ErreurMinuteur("MINUTEUR_DUREE_INVALIDE")
    if len(lister_minuteurs_actifs(user_id)) >= NB_MAX_MINUTEURS_ACTIFS:
        raise ErreurMinuteur("MINUTEUR_TROP_NOMBREUX")

    # Un identifiant de conversation mal forme est ignore plutot que de
    # faire echouer tout le lancement : le minuteur reste utile sans.
    id_conversation = None
    if conversation_id:
        try:
            id_conversation = str(uuid.UUID(str(conversation_id)))
        except ValueError:
            id_conversation = None

    maintenant = _maintenant()
    try:
        res = (
            supabase.table("minuteurs")
            .insert(
                {
                    "user_id": user_id,
                    "conversation_id": id_conversation,
                    "titre": _nettoyer_texte(titre, LONGUEUR_MAX_TITRE),
                    "duree_secondes": duree_secondes,
                    "fin_prevue": (maintenant + timedelta(seconds=duree_secondes)).isoformat(),
                    "action_fin": _nettoyer_texte(action_fin, LONGUEUR_MAX_ACTION_FIN),
                    "lance_par": lance_par,
                }
            )
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (creation minuteur user={user_id}) : {e}")
        raise ErreurMinuteur("MINUTEUR_ECHEC", 500)
    if not res.data:
        raise ErreurMinuteur("MINUTEUR_ECHEC", 500)
    return res.data[0]


def ajuster_minuteur(
    user_id: str,
    minuteur_id: str,
    ajuster_secondes: int = 0,
    titre: str | None = None,
) -> dict:
    """Ajoute (positif) ou retire (negatif) du temps, et/ou change le
    titre. Le minuteur continue sans interruption : seule sa fin prevue
    bouge. Un minuteur dont la fin est deja passee mais pas encore prise
    en charge repart de maintenant plutot que d'un instant deja ecoule."""
    ligne = _lire_ligne(user_id, minuteur_id)
    if ligne is None:
        raise ErreurMinuteur("MINUTEUR_INTROUVABLE", 404)
    if ligne["statut"] != "en_cours":
        raise ErreurMinuteur("MINUTEUR_DEJA_TERMINE", 409)

    maintenant = _maintenant()
    modifications = {"modifie_le": maintenant.isoformat()}

    if ajuster_secondes:
        base = max(_lire_date(ligne["fin_prevue"]), maintenant)
        nouvelle_fin = base + timedelta(seconds=ajuster_secondes)
        restant = (nouvelle_fin - maintenant).total_seconds()
        if not (DUREE_MIN_SECONDES <= restant <= DUREE_MAX_SECONDES):
            raise ErreurMinuteur("MINUTEUR_DUREE_INVALIDE")
        modifications["fin_prevue"] = nouvelle_fin.isoformat()
        # La duree totale suit (l'anneau de l'affichage se vide par
        # rapport a elle) sans jamais tomber sous le temps restant.
        modifications["duree_secondes"] = max(ligne["duree_secondes"] + ajuster_secondes, int(restant))
        # Nouvelle fin : une notification deja envoyee ne vaut plus.
        modifications["notification_envoyee"] = False

    if titre is not None:
        modifications["titre"] = _nettoyer_texte(titre, LONGUEUR_MAX_TITRE)

    try:
        res = (
            supabase.table("minuteurs")
            .update(modifications)
            .eq("id", minuteur_id)
            .eq("user_id", user_id)
            .eq("statut", "en_cours")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (ajustement minuteur {minuteur_id}) : {e}")
        raise ErreurMinuteur("MINUTEUR_ECHEC", 500)
    if not res.data:
        # Termine ou arrete entre la lecture et l'ecriture.
        raise ErreurMinuteur("MINUTEUR_DEJA_TERMINE", 409)
    return res.data[0]


def arreter_minuteur(user_id: str, minuteur_id: str) -> dict:
    try:
        uuid.UUID(str(minuteur_id))
    except ValueError:
        raise ErreurMinuteur("MINUTEUR_INTROUVABLE", 404)
    try:
        res = (
            supabase.table("minuteurs")
            .update({"statut": "arrete", "modifie_le": _maintenant().isoformat()})
            .eq("id", minuteur_id)
            .eq("user_id", user_id)
            .eq("statut", "en_cours")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (arret minuteur {minuteur_id}) : {e}")
        raise ErreurMinuteur("MINUTEUR_ECHEC", 500)
    if res.data:
        return res.data[0]
    if _lire_ligne(user_id, minuteur_id) is None:
        raise ErreurMinuteur("MINUTEUR_INTROUVABLE", 404)
    raise ErreurMinuteur("MINUTEUR_DEJA_TERMINE", 409)


def terminer_minuteur(user_id: str, minuteur_id: str) -> tuple[bool, dict]:
    """Prise en charge de la fin d'un minuteur, une seule fois.

    Renvoie (True, ligne) au SEUL appelant qui obtient la prise en charge :
    c'est celui-la, et lui seul, qui reveille Clovis. Tous les autres
    (autre appareil ouvert en meme temps, deuxieme appel) recoivent
    (False, ligne) et ne doivent rien faire. Aussi (False, ligne) si le
    minuteur n'est pas encore arrive a zero cote serveur (horloge de
    l'appareil en avance au-dela de la tolerance).
    """
    limite = _maintenant() + timedelta(seconds=TOLERANCE_FIN_SECONDES)
    try:
        uuid.UUID(str(minuteur_id))
    except ValueError:
        raise ErreurMinuteur("MINUTEUR_INTROUVABLE", 404)
    try:
        res = (
            supabase.table("minuteurs")
            .update({"statut": "termine", "modifie_le": _maintenant().isoformat()})
            .eq("id", minuteur_id)
            .eq("user_id", user_id)
            .eq("statut", "en_cours")
            .lte("fin_prevue", limite.isoformat())
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (fin minuteur {minuteur_id}) : {e}")
        raise ErreurMinuteur("MINUTEUR_ECHEC", 500)
    if res.data:
        return True, res.data[0]
    ligne = _lire_ligne(user_id, minuteur_id)
    if ligne is None:
        raise ErreurMinuteur("MINUTEUR_INTROUVABLE", 404)
    return False, ligne


def traiter_minuteurs_a_notifier() -> int:
    """Appele par le planificateur (api/main.py) : previent l'etudiant par
    notification quand un minuteur est fini et que personne ne l'a pris
    en charge (appli fermee). Chaque minuteur est reserve AVANT l'envoi,
    donc jamais deux notifications pour le meme, meme si le planificateur
    tourne sur plusieurs instances. Renvoie le nombre de notifications
    traitees."""
    from core.notifications_push import envoyer_notification_push

    seuil = _maintenant() - timedelta(seconds=DELAI_AVANT_NOTIFICATION_SECONDES)
    try:
        res = (
            supabase.table("minuteurs")
            .select("id, user_id, titre")
            .eq("statut", "en_cours")
            .eq("notification_envoyee", False)
            .lte("fin_prevue", seuil.isoformat())
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture minuteurs a notifier) : {e}")
        return 0

    traites = 0
    for ligne in res.data or []:
        try:
            reservation = (
                supabase.table("minuteurs")
                .update({"notification_envoyee": True})
                .eq("id", ligne["id"])
                .eq("notification_envoyee", False)
                .eq("statut", "en_cours")
                .execute()
            )
            if not reservation.data:
                continue  # pris par une autre instance, ou termine entretemps
            corps = ligne.get("titre") or "Ton minuteur est terminé."
            envoyer_notification_push(ligne["user_id"], "Minuteur terminé", corps, "/chat")
            traites += 1
        except Exception as e:
            logging.error(f"ERREUR notification minuteur id={ligne['id']} : {e}")
    return traites
