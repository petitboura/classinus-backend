"""
Liste d'attente des modeles "Bientot" (16/11/2026, demande de Bourama).

Une fausse porte mesure la demande reelle avant de brancher Claude, GPT et Gemini : un clic sur un
modele grise du selecteur ouvre un formulaire (palier, profil, consentement). Aucun paiement n'est
pris. Ce module garde toute la logique ; api/liste_attente.py n'est que la couche HTTP.

Tables (voir migrations/2026_11_16_liste_attente_modeles.sql) :
- paliers_liste_attente : les paliers proposes, lus ici, jamais ecrits en dur.
- liste_attente_modeles : UNE seule ligne par utilisateur (17/11/2026, demande de Bourama : une
  seule liste d'attente, pas une par modele). modele_id garde le modele sur lequel la personne a
  clique en s'inscrivant (le modele d'origine) ; une nouvelle inscription ou une modification ne le
  change pas.
- evenements_liste_attente : les quatre etapes de l'entonnoir, pour les chiffres investisseurs.
- Les textes du formulaire sont dans textes_modeles_llm (cles attente_*), en francais et en anglais.

Les adresses de la table acces_anticipe_modeles voient deja les modeles : leurs inscriptions ne
mesurent pas la meme chose. Le formulaire n'est de toute facon pas ouvert pour elles (elles
n'ont pas de modele grise), donc rien de special a faire ici.
"""

import logging
from datetime import datetime, timezone

from api.auth import supabase

PROFILS = ("etudiant", "administration", "dev")
ETAPES = ("selecteur_ouvert", "modele_grise_clique", "formulaire_ouvert", "inscription_validee")
LANGUES = ("fr", "en")
SOURCES = ("web", "android", "ios", "pc")
LONGUEUR_MAX_MODELE_ID = 120
LONGUEUR_MAX_PAYS = 80
LONGUEUR_MAX_WHATSAPP = 32
PREFIXE_TEXTES = "attente_"


class ErreurListeAttente(Exception):
    """Erreur metier portant un code stable de core/erreurs.py et le statut HTTP a utiliser."""

    def __init__(self, code: str, statut_http: int = 400):
        super().__init__(code)
        self.code = code
        self.statut_http = statut_http


def _nettoyer(valeur, longueur_max: int):
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte[:longueur_max] if texte else None


def _modele_id_valide(modele_id) -> str:
    modele = _nettoyer(modele_id, LONGUEUR_MAX_MODELE_ID)
    if not modele:
        raise ErreurListeAttente("LISTE_ATTENTE_MODELE_INVALIDE")
    return modele


def _langue(langue) -> str | None:
    return langue if langue in LANGUES else None


def _source(source) -> str | None:
    return source if source in SOURCES else None


def lister_paliers() -> list[dict]:
    try:
        res = (
            supabase.table("paliers_liste_attente")
            .select("prix_usd, credit_usd, ordre")
            .eq("actif", True)
            .order("ordre")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture paliers liste d'attente) : {e}")
        raise ErreurListeAttente("LISTE_ATTENTE_ECHEC", 500)
    return res.data or []


def lire_textes() -> dict:
    """Textes du formulaire, par langue : {"fr": {cle: texte}, "en": {cle: texte}}."""
    try:
        res = (
            supabase.table("textes_modeles_llm")
            .select("cle, langue, texte")
            .like("cle", f"{PREFIXE_TEXTES}%")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture textes liste d'attente) : {e}")
        raise ErreurListeAttente("LISTE_ATTENTE_ECHEC", 500)
    textes: dict[str, dict[str, str]] = {}
    for ligne in res.data or []:
        textes.setdefault(ligne["langue"], {})[ligne["cle"]] = ligne["texte"]
    return textes


def lire_inscription(user_id: str) -> dict | None:
    """Inscription active de l'utilisateur (une seule liste) : le formulaire s'en sert pour dire "deja inscrit"."""
    try:
        res = (
            supabase.table("liste_attente_modeles")
            .select("modele_id, palier_prix, profil, statut")
            .eq("user_id", user_id)
            .eq("statut", "actif")
            .limit(1)
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture inscription liste d'attente user={user_id}) : {e}")
        raise ErreurListeAttente("LISTE_ATTENTE_ECHEC", 500)
    lignes = res.data or []
    return lignes[0] if lignes else None


def charger_config(user_id: str) -> dict:
    return {
        "paliers": lister_paliers(),
        "textes": lire_textes(),
        "inscription": lire_inscription(user_id),
        "profils": list(PROFILS),
    }


def inscrire(
    user_id: str,
    email: str | None,
    modele_id,
    palier_prix,
    profil,
    consentement,
    pays=None,
    whatsapp=None,
    langue=None,
    source=None,
) -> dict:
    """Cree ou met a jour l'unique inscription de l'utilisateur ; modele_id est le modele clique."""
    modele = _modele_id_valide(modele_id)
    if profil not in PROFILS:
        raise ErreurListeAttente("LISTE_ATTENTE_PROFIL_INVALIDE")
    if consentement is not True:
        raise ErreurListeAttente("LISTE_ATTENTE_CONSENTEMENT_REQUIS")
    prix_valides = {p["prix_usd"] for p in lister_paliers()}
    if palier_prix not in prix_valides:
        raise ErreurListeAttente("LISTE_ATTENTE_PALIER_INVALIDE")

    maintenant = datetime.now(timezone.utc).isoformat()
    ligne = {
        "user_id": user_id,
        "email": _nettoyer(email, 254),
        "palier_prix": palier_prix,
        "profil": profil,
        "pays": _nettoyer(pays, LONGUEUR_MAX_PAYS),
        "whatsapp": _nettoyer(whatsapp, LONGUEUR_MAX_WHATSAPP),
        "langue": _langue(langue),
        "source": _source(source),
        "consentement": True,
        "consentement_le": maintenant,
        "statut": "actif",
        "modifie_a": maintenant,
    }
    modele_origine = modele
    try:
        existant = (
            supabase.table("liste_attente_modeles").select("modele_id").eq("user_id", user_id).limit(1).execute()
        ).data or []
        if existant:
            # Deja sur la liste : on met a jour les choix, le modele d'origine ne change pas.
            modele_origine = existant[0].get("modele_id") or modele
            supabase.table("liste_attente_modeles").update(ligne).eq("user_id", user_id).execute()
        else:
            supabase.table("liste_attente_modeles").insert({**ligne, "modele_id": modele}).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (inscription liste d'attente user={user_id} modele={modele}) : {e}")
        raise ErreurListeAttente("LISTE_ATTENTE_ECHEC", 500)

    enregistrer_evenement(user_id, "inscription_validee", modele, langue, source)
    return {"modele_id": modele_origine, "palier_prix": palier_prix, "profil": profil, "statut": "actif"}


def desinscrire(user_id: str) -> dict:
    """Passe l'inscription en "desinscrit" (la ligne reste pour les statistiques, sans donnee en plus)."""
    try:
        (
            supabase.table("liste_attente_modeles")
            .update(
                {
                    "statut": "desinscrit",
                    "whatsapp": None,
                    "modifie_a": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (desinscription liste d'attente user={user_id}) : {e}")
        raise ErreurListeAttente("LISTE_ATTENTE_ECHEC", 500)
    return {"statut": "desinscrit"}


def enregistrer_evenement(user_id: str, etape, modele_id=None, langue=None, source=None) -> None:
    """Une etape de l'entonnoir. Un echec d'ecriture ne doit jamais gener l'utilisateur : on logue."""
    if etape not in ETAPES:
        raise ErreurListeAttente("LISTE_ATTENTE_ETAPE_INVALIDE")
    try:
        supabase.table("evenements_liste_attente").insert(
            {
                "user_id": user_id,
                "etape": etape,
                "modele_id": _nettoyer(modele_id, LONGUEUR_MAX_MODELE_ID),
                "langue": _langue(langue),
                "source": _source(source),
            }
        ).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (evenement liste d'attente {etape} user={user_id}) : {e}")
