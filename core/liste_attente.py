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
import re
from datetime import datetime, timezone

from api.auth import supabase

PROFILS = ("etudiant", "administration", "dev")
ETAPES = ("selecteur_ouvert", "modele_grise_clique", "formulaire_ouvert", "inscription_validee")
LANGUES = ("fr", "en")
SOURCES = ("web", "android", "ios", "pc")
LONGUEUR_MAX_MODELE_ID = 120
LONGUEUR_MAX_PAYS = 80
LONGUEUR_MAX_WHATSAPP = 32
LONGUEUR_MAX_MOYEN_PAIEMENT = 40
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


def lister_moyens_paiement() -> list[str]:
    """
    Identifiants des moyens de paiement proposes apres le clic sur Payer (19/11/2026, demande de Bourama).
    La liste vit dans la table moyens_paiement_liste_attente, modifiable sans code. Un echec de lecture ne
    doit jamais empecher la page de s'afficher : on logue et on renvoie une liste vide.
    """
    try:
        res = (
            supabase.table("moyens_paiement_liste_attente")
            .select("id, ordre")
            .eq("actif", True)
            .order("ordre")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture moyens de paiement liste d'attente) : {e}")
        return []
    return [ligne["id"] for ligne in (res.data or []) if ligne.get("id")]


def noms_modeles_par_palier() -> dict[str, list[str]]:
    """
    {palier: [noms de modeles]} lu dans la vraie table (modeles_llm via core/fournisseurs_llm.py), dans l'ordre des
    fournisseurs de Supabase, un modele une seule fois. Les textes de la page des abonnements s'en servent par le
    repere {modeles:<palier>} (par exemple {modeles:ultra}) : les listes de noms ne sont plus ecrites a la main dans les
    textes, donc elles ne peuvent plus s'ecarter du classement reel (19/11/2026, demande de Bourama).
    """
    try:
        from core import fournisseurs_llm

        config = fournisseurs_llm._config_modeles()
        par_palier: dict[str, list[str]] = {palier: [] for palier in config["paliers"]}
        deja_vus: set[str] = set()
        for distributeur in config["distributeurs"]:
            for palier in config["paliers"]:
                info = config["modeles"].get(distributeur, {}).get(palier)
                if not info or info["id"] in deja_vus:
                    continue
                deja_vus.add(info["id"])
                par_palier[palier].append(info["label"])
        return par_palier
    except Exception as e:
        logging.error(f"ERREUR (lecture des modeles par palier pour les textes des abonnements) : {e}")
        return {}


_REPERE_MODELES = re.compile(r"\{modeles:([a-z_]+)\}")


def remplir_reperes_modeles(texte: str, par_palier: dict[str, list[str]]) -> str:
    """Remplace {modeles:<palier>} par les noms du palier, separes par des virgules. Sans nom (palier vide ou lecture
    qui echoue), le repere disparait avec ses parentheses plutot que d'afficher « {modeles:...} » a l'ecran."""
    if "{modeles:" not in texte:
        return texte
    rempli = _REPERE_MODELES.sub(lambda m: ", ".join(par_palier.get(m.group(1), [])), texte)
    return re.sub(r"\s*\(\s*\)", "", rempli)


def lire_textes() -> dict:
    """Textes du formulaire, par langue : {"fr": {cle: texte}, "en": {cle: texte}}. Les reperes {modeles:<palier>} y
    sont remplis avec les vrais modeles de chaque palier."""
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
    if any("{modeles:" in t for langue in textes.values() for t in langue.values()):
        par_palier = noms_modeles_par_palier()
        textes = {
            langue: {cle: remplir_reperes_modeles(t, par_palier) for cle, t in textes_langue.items()}
            for langue, textes_langue in textes.items()
        }
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


def lister_modeles_publics() -> list[dict]:
    """
    Modeles montres sur la page des abonnements (19/11/2026, demande de Bourama), groupes par
    entreprise : [{"distributeur", "nom", "modeles": [{"label", "groupe", "badge"}]}].

    Meme source que le selecteur du chat (tables fournisseurs_llm et modeles_llm de Supabase, via
    core/fournisseurs_llm.py) : rien n'est ecrit ici. Ordre des entreprises = ordre de Supabase,
    modeles du plus puissant au moins puissant. Une lecture qui echoue ne casse pas la page : la
    liste est alors vide et le front n'affiche simplement pas le tableau des modeles.
    """
    try:
        from core import fournisseurs_llm

        config = fournisseurs_llm._config_modeles()
        groupes = []
        for distributeur in config["distributeurs"]:
            modeles = []
            for palier in reversed(config["paliers"]):
                info = config["modeles"].get(distributeur, {}).get(palier)
                if not info:
                    continue
                groupe = info.get("groupe")
                modeles.append({
                    "label": info["label"],
                    "groupe": groupe,
                    "badge": fournisseurs_llm.libelles_badge(groupe),
                })
            if modeles:
                nom = config["fournisseurs"][distributeur].get("nom_affiche") or distributeur
                groupes.append({"distributeur": distributeur, "nom": nom, "modeles": modeles})
        return groupes
    except Exception as e:
        logging.error(f"ERREUR (lecture des modeles pour la page des abonnements) : {e}")
        return []


def charger_config(user_id: str | None) -> dict:
    """user_id vaut None pour un visiteur sans compte : il voit les paliers, jamais d'inscription."""
    return {
        "paliers": lister_paliers(),
        "textes": lire_textes(),
        "inscription": lire_inscription(user_id) if user_id else None,
        "profils": list(PROFILS),
        "moyens_paiement": lister_moyens_paiement(),
        "modeles": lister_modeles_publics(),
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
    moyen_paiement=None,
) -> dict:
    """Cree ou met a jour l'unique inscription de l'utilisateur ; modele_id est le modele clique."""
    modele = _modele_id_valide(modele_id)
    # Le profil est facultatif depuis le parcours de paiement (19/11/2026) : absent, on n'en garde pas.
    if profil is not None and profil not in PROFILS:
        raise ErreurListeAttente("LISTE_ATTENTE_PROFIL_INVALIDE")
    if consentement is not True:
        raise ErreurListeAttente("LISTE_ATTENTE_CONSENTEMENT_REQUIS")
    prix_valides = {p["prix_usd"] for p in lister_paliers()}
    if palier_prix not in prix_valides:
        raise ErreurListeAttente("LISTE_ATTENTE_PALIER_INVALIDE")
    moyen = _nettoyer(moyen_paiement, LONGUEUR_MAX_MOYEN_PAIEMENT)
    if moyen is not None and moyen not in lister_moyens_paiement():
        raise ErreurListeAttente("LISTE_ATTENTE_MOYEN_PAIEMENT_INVALIDE")

    maintenant = datetime.now(timezone.utc).isoformat()
    ligne = {
        "user_id": user_id,
        "email": _nettoyer(email, 254),
        "palier_prix": palier_prix,
        "profil": profil,
        "pays": _nettoyer(pays, LONGUEUR_MAX_PAYS),
        "moyen_paiement": moyen,
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
