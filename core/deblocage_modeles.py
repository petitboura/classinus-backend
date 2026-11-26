"""
Deblocage d'un modele pour tout le monde ou pour une liste d'adresses (26/11/2026, demande de Bourama).

Un modele debloque ici devient choisissable par la personne concernee MEME au-dessus de son palier et MEME
marque Bientot. La cle API du fournisseur reste exigee, et le fournisseur doit etre un de ceux que l'agent
unique ouvre : voir core.fournisseurs_llm.modeles_disponibles_pour_agent, qui lit la table (cache d'environ
1 minute). Ce module ne fait qu'ecrire et lire la table deblocages_modeles ; api/deblocage_modeles.py est la
couche HTTP (routes reservees aux admins).

Table : deblocages_modeles (voir migrations/2026_11_26_deblocages_modeles.sql).
- email NULL = tout le monde (y compris un visiteur sans compte) ; sinon une adresse, en minuscules.
- Actif = non revoque ET (sans date de fin OU date de fin dans le futur). Une revocation garde la ligne.
- Les deblocages s'ajoutent. Redonner un deblocage deja actif ne cree pas de doublon.
"""

import logging
import re
from datetime import datetime, timezone

from api.auth import supabase
from core.deblocage_paliers import ErreurDeblocage, _en_utc, _lire_date, _maintenant
from core.fournisseurs_llm import ids_des_modeles, reinitialiser_cache_config_modeles

LONGUEUR_MAX_MOTIF = 500
ADRESSES_MAX_PAR_APPEL = 200
LONGUEUR_MAX_ADRESSE = 254
_FORME_ADRESSE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normaliser_adresses(adresses) -> list[str]:
    """Adresses en minuscules, sans espaces ni doublons, dans l'ordre donne. Une adresse mal formee refuse tout l'appel."""
    vues, resultat = set(), []
    for brute in adresses or []:
        adresse = str(brute or "").strip().lower()
        if not adresse or len(adresse) > LONGUEUR_MAX_ADRESSE or not _FORME_ADRESSE.match(adresse):
            raise ErreurDeblocage("DEBLOCAGE_MODELE_EMAIL_INVALIDE")
        if adresse not in vues:
            vues.add(adresse)
            resultat.append(adresse)
    if len(resultat) > ADRESSES_MAX_PAR_APPEL:
        raise ErreurDeblocage("DEBLOCAGE_MODELE_TROP_ADRESSES")
    return resultat


def _verifier_cible(tous: bool, adresses: list[str]) -> None:
    """Exactement une cible : tout le monde, ou une liste d'adresses (jamais les deux, jamais aucune)."""
    if bool(tous) == bool(adresses):
        raise ErreurDeblocage("DEBLOCAGE_MODELE_CIBLE_INVALIDE")


def _lignes_actives(modele_id: str | None = None) -> list[dict]:
    try:
        requete = (
            supabase.table("deblocages_modeles")
            .select("id, modele_id, email, motif, debut, expire_le")
            .is_("revoque_le", "null")
        )
        if modele_id:
            requete = requete.eq("modele_id", modele_id)
        lignes = requete.execute().data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture des deblocages de modeles) : {e}")
        raise ErreurDeblocage("DEBLOCAGE_ECHEC", 500)
    maintenant = _maintenant()
    actives = []
    for ligne in lignes:
        fin = _lire_date(ligne.get("expire_le"))
        if fin is None or fin > maintenant:
            actives.append(ligne)
    return actives


def lister(modele_id: str | None = None) -> dict:
    """Les deblocages actifs (d'un modele, ou de tous), regroupes par modele."""
    par_modele: dict[str, dict] = {}
    for ligne in _lignes_actives(modele_id):
        groupe = par_modele.setdefault(ligne["modele_id"], {"modele_id": ligne["modele_id"], "tous": False, "adresses": []})
        if ligne.get("email") is None:
            groupe["tous"] = True
        else:
            groupe["adresses"].append(ligne["email"])
    for groupe in par_modele.values():
        groupe["adresses"].sort()
    return {"deblocages": sorted(par_modele.values(), key=lambda g: g["modele_id"])}


def debloquer_modele(
    modele_id: str,
    tous: bool = False,
    adresses=None,
    accorde_par: str | None = None,
    motif: str | None = None,
    expire_le: datetime | None = None,
) -> dict:
    """Debloque un modele pour tout le monde ou pour une liste d'adresses."""
    modele_id = (modele_id or "").strip()
    if modele_id not in ids_des_modeles():
        raise ErreurDeblocage("DEBLOCAGE_MODELE_INCONNU")
    liste = normaliser_adresses(adresses)
    _verifier_cible(tous, liste)
    fin = None
    if expire_le is not None:
        fin = _en_utc(expire_le)
        if fin <= _maintenant():
            raise ErreurDeblocage("DEBLOCAGE_DATE_INVALIDE")
    motif_net = (motif or "").strip()[:LONGUEUR_MAX_MOTIF] or None

    deja = _lignes_actives(modele_id)
    deja_pour_tous = any(ligne.get("email") is None for ligne in deja)
    deja_adresses = {ligne["email"] for ligne in deja if ligne.get("email") is not None}

    cibles = [None] if tous else liste
    a_ajouter = [c for c in cibles if not (deja_pour_tous if c is None else c in deja_adresses)]
    deja_actifs = [c for c in cibles if c not in a_ajouter]
    lignes = [
        {
            "modele_id": modele_id,
            "email": cible,
            "accorde_par": accorde_par,
            "motif": motif_net,
            "expire_le": fin.isoformat() if fin else None,
        }
        for cible in a_ajouter
    ]
    if lignes:
        try:
            supabase.table("deblocages_modeles").insert(lignes).execute()
        except Exception as e:
            logging.error(f"ERREUR SUPABASE (deblocage du modele {modele_id}) : {e}")
            raise ErreurDeblocage("DEBLOCAGE_ECHEC", 500)
        reinitialiser_cache_config_modeles()
    return {
        "modele_id": modele_id,
        "ajoutes": len(lignes),
        # None (= tout le monde) devient le mot "tous" pour la reponse.
        "deja_actifs": ["tous" if c is None else c for c in deja_actifs],
    }


def revoquer_modele(modele_id: str, tous: bool = False, adresses=None) -> dict:
    """Revoque les deblocages actifs d'un modele pour tout le monde ou pour une liste d'adresses."""
    modele_id = (modele_id or "").strip()
    if not modele_id:
        raise ErreurDeblocage("DEBLOCAGE_MODELE_INCONNU")
    liste = normaliser_adresses(adresses)
    _verifier_cible(tous, liste)
    try:
        requete = (
            supabase.table("deblocages_modeles")
            .update({"revoque_le": datetime.now(timezone.utc).isoformat()})
            .eq("modele_id", modele_id)
            .is_("revoque_le", "null")
        )
        requete = requete.is_("email", "null") if tous else requete.in_("email", liste)
        res = requete.execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (revocation du deblocage du modele {modele_id}) : {e}")
        raise ErreurDeblocage("DEBLOCAGE_ECHEC", 500)
    reinitialiser_cache_config_modeles()
    return {"modele_id": modele_id, "revoques": len(res.data or []) if res is not None else 0}
