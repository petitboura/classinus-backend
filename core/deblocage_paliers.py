"""
Deblocage de palier par personne (25/11/2026, demande de Bourama).

REGLE : Classinus n'a qu'UN SEUL agent. Un palier appartient a la PERSONNE, jamais a un agent. Ce module
garde toute la logique ; api/deblocage_paliers.py n'est que la couche HTTP (routes reservees aux admins).

Aujourd'hui un administrateur debloque un palier a la main. Plus tard, le webhook de paiement appellera
`debloquer(..., source="paiement")` : rien d'autre ne changera. Aucun fournisseur de paiement n'est branche ici.

Table : deblocages_paliers (voir migrations/2026_11_25_deblocages_paliers.sql).
- Actif = non revoque ET (sans date de fin OU date de fin dans le futur).
- Le palier d'une personne est le plus haut de ses deblocages actifs, dans l'ordre des paliers de la
  configuration Supabase (core.fournisseurs_llm.ordre_des_paliers), jamais un ordre ecrit en dur ici.
- Les deblocages s'ajoutent : en accorder un nouveau n'en retire aucun. Une revocation garde la ligne.

Cette etape ne branche PAS encore le palier debloque sur l'acces aux modeles du chat : voir
docs/chantiers/DEBLOCAGE_PALIERS.md.
"""

import logging
import uuid
from datetime import datetime, timezone

from api.auth import supabase
from core.fournisseurs_llm import ordre_des_paliers

SOURCES = ("manuel", "paiement")
LONGUEUR_MAX_MOTIF = 500
# Recherche d'une personne par e-mail : l'API Supabase ne sait pas chercher par e-mail, on parcourt donc
# les comptes page par page, avec un plafond (route admin, usage rare). L'identifiant reste le chemin sur.
RECHERCHE_EMAIL_PAR_PAGE = 200
RECHERCHE_EMAIL_PAGES_MAX = 50


class ErreurDeblocage(Exception):
    """Erreur metier portant un code stable de core/erreurs.py et le statut HTTP a utiliser."""

    def __init__(self, code: str, statut_http: int = 400):
        super().__init__(code)
        self.code = code
        self.statut_http = statut_http


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _en_utc(date: datetime) -> datetime:
    """Une date sans fuseau est lue comme UTC (le serveur ne devine pas le fuseau de l'administrateur)."""
    return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)


def _lire_date(valeur) -> datetime | None:
    if not valeur:
        return None
    try:
        return _en_utc(datetime.fromisoformat(str(valeur).replace("Z", "+00:00")))
    except ValueError:
        return None


def _uuid_valide(valeur) -> str:
    try:
        return str(uuid.UUID(str(valeur).strip()))
    except (ValueError, AttributeError):
        raise ErreurDeblocage("DEBLOCAGE_UTILISATEUR_INVALIDE")


def trouver_utilisateur_par_email(email: str) -> str:
    """Identifiant du compte qui porte cet e-mail, ou ErreurDeblocage(DEBLOCAGE_UTILISATEUR_INTROUVABLE)."""
    cherche = (email or "").strip().lower()
    if not cherche:
        raise ErreurDeblocage("DEBLOCAGE_UTILISATEUR_INVALIDE")
    for page in range(1, RECHERCHE_EMAIL_PAGES_MAX + 1):
        try:
            utilisateurs = supabase.auth.admin.list_users(page=page, per_page=RECHERCHE_EMAIL_PAR_PAGE)
        except Exception as e:
            logging.error(f"ERREUR SUPABASE (recherche d'un compte par e-mail, page {page}) : {e}")
            raise ErreurDeblocage("DEBLOCAGE_ECHEC", 500)
        for utilisateur in utilisateurs or []:
            if (getattr(utilisateur, "email", None) or "").strip().lower() == cherche:
                return str(utilisateur.id)
        if not utilisateurs or len(utilisateurs) < RECHERCHE_EMAIL_PAR_PAGE:
            break
    raise ErreurDeblocage("DEBLOCAGE_UTILISATEUR_INTROUVABLE", 404)


def resoudre_utilisateur(user_id: str | None, email: str | None) -> str:
    """Exactement un des deux est attendu : l'identifiant du compte ou son e-mail."""
    if bool(user_id) == bool(email):
        raise ErreurDeblocage("DEBLOCAGE_UTILISATEUR_INVALIDE")
    return _uuid_valide(user_id) if user_id else trouver_utilisateur_par_email(email)


def _verifier_compte_existe(user_id: str) -> None:
    try:
        reponse = supabase.auth.admin.get_user_by_id(user_id)
    except Exception as e:
        # Un identifiant inconnu fait lever une erreur cote Supabase : on la traite comme "introuvable".
        logging.error(f"ERREUR SUPABASE (verification du compte {user_id}) : {e}")
        raise ErreurDeblocage("DEBLOCAGE_UTILISATEUR_INTROUVABLE", 404)
    if not reponse or not getattr(reponse, "user", None):
        raise ErreurDeblocage("DEBLOCAGE_UTILISATEUR_INTROUVABLE", 404)


def _resume(ligne: dict) -> dict:
    return {
        "id": ligne.get("id"),
        "palier": ligne.get("palier"),
        "source": ligne.get("source"),
        "motif": ligne.get("motif"),
        "debut": ligne.get("debut"),
        "expire_le": ligne.get("expire_le"),
    }


def deblocages_actifs(user_id: str) -> list[dict]:
    """Les deblocages actifs de la personne (non revoques et non expires), tels qu'ils sont en base."""
    try:
        res = (
            supabase.table("deblocages_paliers")
            .select("id, palier, source, motif, debut, expire_le")
            .eq("user_id", user_id)
            .is_("revoque_le", "null")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture des deblocages de {user_id}) : {e}")
        raise ErreurDeblocage("DEBLOCAGE_ECHEC", 500)
    maintenant = _maintenant()
    actifs = []
    for ligne in res.data or []:
        fin = _lire_date(ligne.get("expire_le"))
        if fin is None or fin > maintenant:
            actifs.append(ligne)
    return actifs


def _plus_haut_palier(lignes: list[dict], user_id: str) -> str | None:
    ordre = ordre_des_paliers()
    meilleur = None
    for ligne in lignes:
        palier = ligne.get("palier")
        if palier not in ordre:
            # Un palier retire de la configuration ne donne plus rien : on le signale, sans bloquer le reste.
            logging.error(f"Deblocage de palier inconnu ignore : {palier} (personne {user_id})")
            continue
        if meilleur is None or ordre.index(palier) > ordre.index(meilleur):
            meilleur = palier
    return meilleur


def palier_debloque_de(user_id: str) -> str | None:
    """Le plus haut palier actif de la personne, ou None si rien n'est debloque."""
    return _plus_haut_palier(deblocages_actifs(user_id), user_id)


def debloquer(
    user_id: str,
    palier: str,
    accorde_par: str | None = None,
    motif: str | None = None,
    expire_le: datetime | None = None,
    source: str = "manuel",
) -> dict:
    """Accorde un palier a une personne. Le futur webhook de paiement appellera cette fonction."""
    if source not in SOURCES:
        raise ErreurDeblocage("DEBLOCAGE_SOURCE_INVALIDE")
    if palier not in ordre_des_paliers():
        raise ErreurDeblocage("DEBLOCAGE_PALIER_INVALIDE")
    fin = None
    if expire_le is not None:
        fin = _en_utc(expire_le)
        if fin <= _maintenant():
            raise ErreurDeblocage("DEBLOCAGE_DATE_INVALIDE")
    user_id = _uuid_valide(user_id)
    _verifier_compte_existe(user_id)
    motif_net = (motif or "").strip()[:LONGUEUR_MAX_MOTIF] or None
    ligne = {
        "user_id": user_id,
        "palier": palier,
        "source": source,
        "accorde_par": accorde_par,
        "motif": motif_net,
        "expire_le": fin.isoformat() if fin else None,
    }
    try:
        res = supabase.table("deblocages_paliers").insert(ligne).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (deblocage du palier {palier} pour {user_id}) : {e}")
        raise ErreurDeblocage("DEBLOCAGE_ECHEC", 500)
    cree = (res.data or [{}])[0] if res is not None else {}
    return _resume({**ligne, **cree})


def revoquer(user_id: str) -> dict:
    """Revoque tous les deblocages actifs de la personne. Les lignes restent en base (historique)."""
    user_id = _uuid_valide(user_id)
    try:
        res = (
            supabase.table("deblocages_paliers")
            .update({"revoque_le": _maintenant().isoformat()})
            .eq("user_id", user_id)
            .is_("revoque_le", "null")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (revocation des deblocages de {user_id}) : {e}")
        raise ErreurDeblocage("DEBLOCAGE_ECHEC", 500)
    return {"revoques": len(res.data or []) if res is not None else 0}


def etat(user_id: str) -> dict:
    """Ce que l'administrateur voit pour une personne : ses deblocages actifs et le plus haut palier."""
    user_id = _uuid_valide(user_id)
    actifs = deblocages_actifs(user_id)
    return {
        "user_id": user_id,
        "palier_debloque": _plus_haut_palier(actifs, user_id),
        "deblocages": [_resume(ligne) for ligne in actifs],
    }
