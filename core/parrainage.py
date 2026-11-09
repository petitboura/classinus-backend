"""Parrainage : un compte invité par un lien rapporte des crédits d'images à son parrain.

Toute la logique vit dans des fonctions SQL atomiques (migration 2026_11_09_parrainage_fonctions.sql) :
deux appels en même temps pour le même filleul passent l'un après l'autre, et le parrain n'est crédité
qu'une seule fois par filleul. Le gain par filleul, le solde de départ et la fenêtre pendant laquelle un
compte peut être parrainé se règlent dans la table parrainage_reglages, sans toucher au code.

Déroulé :
1. Le frontend garde le code du lien, puis appelle POST /api/parrainage/enregistrer quand la personne
   est connectée (donc, avec « Confirm email » actif dans Supabase, une fois son email confirmé).
2. enregistrer_parrainage renvoie le statut : valide (parrain crédité), en_attente (email pas encore
   confirmé, un nouvel appel le ré-évalue), refuse, ou ignore (code inconnu, auto-parrainage, compte
   trop ancien). Le motif exact reste dans les logs : il n'est jamais donné à la personne, pour ne pas
   expliquer comment contourner les règles.
"""
import logging


class ErreurParrainage(Exception):
    """Erreur destinée à l'utilisateur : un code stable, traduit en français et en anglais dans
    core/erreurs.py (et lib/erreurs.ts côté frontend), jamais un texte écrit en dur ici."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


STATUTS = ("valide", "en_attente", "refuse", "ignore")
LONGUEUR_MAX_CODE = 32


def enregistrer_parrainage(client_base, user_id, code) -> dict:
    """Enregistre le parrain d'un compte et, si les conditions sont réunies, crédite le parrain.

    Renvoie {"statut": ...}. Ne renvoie jamais le motif d'un refus. Si la base ne répond pas, on lève
    une erreur : le frontend peut réessayer, rien n'a été crédité.
    """
    if not user_id:
        raise ErreurParrainage("PARRAINAGE_INDISPONIBLE")
    code_propre = (code or "").strip()
    if not code_propre or len(code_propre) > LONGUEUR_MAX_CODE:
        raise ErreurParrainage("PARRAINAGE_CODE_INVALIDE")
    try:
        reponse = client_base.rpc(
            "parrainage_enregistrer", {"p_filleul": user_id, "p_code": code_propre}
        ).execute()
    except Exception as e:
        logging.error("ERREUR SUPABASE (enregistrement parrainage pour %s) : %s", user_id, e)
        raise ErreurParrainage("PARRAINAGE_INDISPONIBLE")
    donnees = reponse.data
    if not isinstance(donnees, dict) or donnees.get("statut") not in STATUTS:
        logging.error("ERREUR SUPABASE (parrainage, réponse inattendue pour %s) : %r", user_id, donnees)
        raise ErreurParrainage("PARRAINAGE_INDISPONIBLE")
    if donnees["statut"] in ("refuse", "ignore"):
        logging.info("Parrainage non retenu pour %s : %s (%s)", user_id, donnees["statut"], donnees.get("motif"))
    return {"statut": donnees["statut"]}


def resume_parrainage(client_base, user_id) -> dict:
    """Ce que le compte voit de son parrainage : son code, son solde de crédits et ses filleuls."""
    if not user_id:
        raise ErreurParrainage("PARRAINAGE_INDISPONIBLE")
    try:
        reponse = client_base.rpc("parrainage_resume", {"p_user": user_id}).execute()
    except Exception as e:
        logging.error("ERREUR SUPABASE (résumé parrainage pour %s) : %s", user_id, e)
        raise ErreurParrainage("PARRAINAGE_INDISPONIBLE")
    donnees = reponse.data
    if not isinstance(donnees, dict) or not donnees.get("code"):
        logging.error("ERREUR SUPABASE (résumé parrainage, réponse inattendue pour %s) : %r", user_id, donnees)
        raise ErreurParrainage("PARRAINAGE_INDISPONIBLE")
    return {
        "code": donnees["code"],
        "solde": donnees.get("solde", 0),
        "filleuls_valides": donnees.get("filleuls_valides", 0),
        "filleuls_en_attente": donnees.get("filleuls_en_attente", 0),
    }
