"""Page bambara : profils, historique des conversations et éléments gardés (18/11/2026).

Quatre tables (migration 2026_11_18_page_bambara_profils_historique.sql) : bambara_profils,
bambara_conversations, bambara_audios et bambara_gardes. Elles suivent le compte (ON DELETE CASCADE)
et ne sont lues ou écrites que par le backend.

Un « profil » est une personne qui se sert du compte : un nom et un prénom, rien d'autre. Quand aucun
profil n'est choisi, les conversations et les éléments gardés appartiennent à un espace commun du
compte (profil_id vide). Un profil appartient toujours au compte qui l'a créé : chaque fonction
vérifie le propriétaire avant de lire ou d'écrire.

Les erreurs sont des codes stables traduits dans core/erreurs.py (français et anglais) et dans
lib/erreurs.ts côté frontend, jamais des textes écrits ici.
"""
import base64
import binascii
import logging
import re
import uuid

LONGUEUR_MAX_NOM = 60
MAX_PROFILS_PAR_COMPTE = 20
LIMITE_CONVERSATIONS = 30
LIMITE_GARDES = 200
# Environ 1,5 Mo de son avant l'encodage : un vocal de quelques dizaines de secondes en WAV.
LONGUEUR_MAX_AUDIO_BASE64 = 2_000_000
GENRES_GARDES = ("video", "image")
GENRES_PROFIL = ("femme", "homme")
LONGUEUR_MAX_PRESENTATION = 2000
LANGUE_PARCOURS_PAR_DEFAUT = "bm"
_MOTIF_URL = re.compile(r"^https?://\S+$")


class ErreurBambara(Exception):
    """Erreur destinée à l'utilisateur : un code stable traduit dans core/erreurs.py."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _identifiant(valeur, code: str) -> str:
    try:
        return str(uuid.UUID(str(valeur)))
    except (ValueError, AttributeError, TypeError):
        raise ErreurBambara(code)


def normaliser_profil(valeur):
    """Identifiant de profil propre (texte), ou None pour l'espace commun du compte."""
    if valeur is None or str(valeur).strip() == "":
        return None
    return _identifiant(valeur, "BAMBARA_PROFIL_INTROUVABLE")


def _filtre_profil(requete, profil_id):
    """Un profil précis, ou l'espace commun du compte quand aucun profil n'est choisi."""
    return requete.eq("profil_id", profil_id) if profil_id else requete.is_("profil_id", "null")


def _verifier_profil(client, user_id, profil_id) -> None:
    """Le profil existe et appartient bien à ce compte. Un profil vide (espace commun) est toujours permis."""
    if not profil_id:
        return
    try:
        lignes = (
            client.table("bambara_profils").select("id").eq("id", profil_id).eq("user_id", user_id).limit(1).execute().data
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (vérification profil bambara %s pour %s) : %s", profil_id, user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    if not lignes:
        raise ErreurBambara("BAMBARA_PROFIL_INTROUVABLE")


def _nettoyer_nom(valeur) -> str:
    propre = " ".join(str(valeur or "").split())
    if not propre or len(propre) > LONGUEUR_MAX_NOM:
        raise ErreurBambara("BAMBARA_PROFIL_NOM_INVALIDE")
    return propre


def lister_profils(client, user_id) -> list:
    try:
        return (
            client.table("bambara_profils").select("id,nom,prenom,genre,cree_a").eq("user_id", user_id).order("cree_a").execute().data
            or []
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (liste profils bambara pour %s) : %s", user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")


def creer_profil(client, user_id, nom, prenom) -> dict:
    nom_propre = _nettoyer_nom(nom)
    prenom_propre = _nettoyer_nom(prenom)
    existants = lister_profils(client, user_id)
    if len(existants) >= MAX_PROFILS_PAR_COMPTE:
        raise ErreurBambara("BAMBARA_TROP_DE_PROFILS")
    try:
        lignes = (
            client.table("bambara_profils")
            .insert({"user_id": user_id, "nom": nom_propre, "prenom": prenom_propre})
            .execute()
            .data
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (création profil bambara pour %s) : %s", user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    if not lignes:
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    ligne = lignes[0]
    return {"id": ligne["id"], "nom": ligne["nom"], "prenom": ligne["prenom"], "cree_a": ligne["cree_a"]}


def creer_profil_parcours(client, user_id, nom_parle, genre, presentation) -> dict:
    """Profil créé par le parcours d'inscription vocal (22/11/2026) : un seul nom (dit à voix haute puis transcrit),
    le genre (femme ou homme, choisi sur une image) et une présentation facultative (parole transcrite).
    Le nom est rangé dans `prenom`, `nom` reste vide."""
    prenom_propre = _nettoyer_nom_parle(nom_parle)
    if genre not in GENRES_PROFIL:
        raise ErreurBambara("BAMBARA_PROFIL_GENRE_INVALIDE")
    texte = " ".join(str(presentation or "").split())
    if len(texte) > LONGUEUR_MAX_PRESENTATION:
        raise ErreurBambara("BAMBARA_PRESENTATION_INVALIDE")
    if len(lister_profils(client, user_id)) >= MAX_PROFILS_PAR_COMPTE:
        raise ErreurBambara("BAMBARA_TROP_DE_PROFILS")
    ligne_a_ecrire = {"user_id": user_id, "nom": "", "prenom": prenom_propre, "genre": genre}
    if texte:
        ligne_a_ecrire["presentation"] = texte
    try:
        lignes = client.table("bambara_profils").insert(ligne_a_ecrire).execute().data
    except Exception as e:
        logging.error("ERREUR SUPABASE (création profil bambara par parcours pour %s) : %s", user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    if not lignes:
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    ligne = lignes[0]
    return {
        "id": ligne["id"],
        "nom": ligne["nom"],
        "prenom": ligne["prenom"],
        "genre": ligne.get("genre"),
        "cree_a": ligne["cree_a"],
    }


def _nettoyer_nom_parle(valeur) -> str:
    propre = " ".join(str(valeur or "").split())
    if not propre or len(propre) > LONGUEUR_MAX_NOM:
        raise ErreurBambara("BAMBARA_NOM_PARLE_INVALIDE")
    return propre


def lister_textes_parcours(client, langue=None) -> dict:
    """Les phrases du parcours d'inscription (clé vers texte), lues par la voix de Classinus. Elles viennent de la table
    bambara_parcours_textes : aucune n'est écrite dans le code. Une clé absente est simplement absente du résultat."""
    langue_propre = (langue or LANGUE_PARCOURS_PAR_DEFAUT).strip().lower()[:10] or LANGUE_PARCOURS_PAR_DEFAUT
    try:
        lignes = (
            client.table("bambara_parcours_textes").select("cle,texte").eq("langue", langue_propre).eq("actif", True).execute().data
            or []
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (textes du parcours bambara, langue %s) : %s", langue_propre, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    return {l["cle"]: l["texte"] for l in lignes if l.get("cle") and str(l.get("texte") or "").strip()}


def lister_conversations(client, user_id, profil_id) -> list:
    """Les conversations récentes d'un profil, la plus récente d'abord, avec leur premier message."""
    _verifier_profil(client, user_id, profil_id)
    try:
        requete = client.table("bambara_conversations").select("id,texte,a_audio,cree_a").eq("user_id", user_id)
        return _filtre_profil(requete, profil_id).order("cree_a", desc=True).limit(LIMITE_CONVERSATIONS).execute().data or []
    except Exception as e:
        logging.error("ERREUR SUPABASE (liste conversations bambara pour %s) : %s", user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")


def enregistrer_premier_message(client, user_id, conversation_id, profil_id, texte, audio) -> dict:
    """Garde le premier message d'une conversation. Une conversation déjà connue n'est jamais modifiée :
    renvoyer le même premier message deux fois ne change rien.

    `audio` est None ou un dict {base64, duree_ms, pics}."""
    identifiant = _identifiant(conversation_id, "BAMBARA_CONVERSATION_INVALIDE")
    _verifier_profil(client, user_id, profil_id)
    texte_propre = (texte or "").strip()[:2000] or None
    if not texte_propre and not audio:
        raise ErreurBambara("BAMBARA_MESSAGE_VIDE")
    if audio:
        brut = audio.get("base64") or ""
        if len(brut) > LONGUEUR_MAX_AUDIO_BASE64:
            raise ErreurBambara("BAMBARA_AUDIO_INVALIDE")
        try:
            base64.b64decode(brut, validate=True)
        except (binascii.Error, ValueError):
            raise ErreurBambara("BAMBARA_AUDIO_INVALIDE")
        if not brut:
            raise ErreurBambara("BAMBARA_AUDIO_INVALIDE")
    try:
        existantes = client.table("bambara_conversations").select("id,user_id").eq("id", identifiant).limit(1).execute().data
        if existantes:
            if existantes[0]["user_id"] != user_id:
                raise ErreurBambara("BAMBARA_CONVERSATION_INTROUVABLE")
            return {"deja_enregistree": True}
        client.table("bambara_conversations").insert(
            {
                "id": identifiant,
                "user_id": user_id,
                "profil_id": profil_id or None,
                "texte": texte_propre,
                "a_audio": bool(audio),
            }
        ).execute()
        if audio:
            client.table("bambara_audios").insert(
                {
                    "conversation_id": identifiant,
                    "user_id": user_id,
                    "audio_base64": audio["base64"],
                    "duree_ms": max(0, int(audio.get("duree_ms") or 0)),
                    "pics": [round(float(p), 3) for p in (audio.get("pics") or [])][:64],
                }
            ).execute()
    except ErreurBambara:
        raise
    except Exception as e:
        logging.error("ERREUR SUPABASE (premier message bambara %s pour %s) : %s", identifiant, user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    return {"deja_enregistree": False}


def lire_audio(client, user_id, conversation_id) -> dict:
    """Le premier vocal d'une conversation du compte : son en base64, durée et hauteurs des barres."""
    identifiant = _identifiant(conversation_id, "BAMBARA_CONVERSATION_INVALIDE")
    try:
        lignes = (
            client.table("bambara_audios")
            .select("audio_base64,duree_ms,pics")
            .eq("conversation_id", identifiant)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (lecture audio bambara %s pour %s) : %s", identifiant, user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    if not lignes:
        raise ErreurBambara("BAMBARA_CONVERSATION_INTROUVABLE")
    ligne = lignes[0]
    return {"base64": ligne["audio_base64"], "duree_ms": ligne["duree_ms"], "pics": ligne.get("pics") or []}


def lister_gardes(client, user_id, profil_id) -> list:
    """Les vidéos et images gardées d'un profil, les plus récentes d'abord."""
    _verifier_profil(client, user_id, profil_id)
    try:
        requete = client.table("bambara_gardes").select("id,genre,url,titre,miniature,id_video,cree_a").eq("user_id", user_id)
        return _filtre_profil(requete, profil_id).order("cree_a", desc=True).limit(LIMITE_GARDES).execute().data or []
    except Exception as e:
        logging.error("ERREUR SUPABASE (liste gardés bambara pour %s) : %s", user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")


def _garde_existante(client, user_id, profil_id, url):
    requete = client.table("bambara_gardes").select("id,genre,url,titre,miniature,id_video,cree_a").eq("user_id", user_id).eq("url", url)
    lignes = _filtre_profil(requete, profil_id).limit(1).execute().data
    return lignes[0] if lignes else None


def garder(client, user_id, profil_id, genre, url, titre, miniature, id_video) -> dict:
    """Garde une vidéo ou une image. La garder une seconde fois renvoie la même ligne."""
    if genre not in GENRES_GARDES:
        raise ErreurBambara("BAMBARA_GARDE_INVALIDE")
    adresse = (url or "").strip()
    if not adresse or len(adresse) > 2000 or not _MOTIF_URL.match(adresse):
        raise ErreurBambara("BAMBARA_GARDE_INVALIDE")
    vignette = (miniature or "").strip() or None
    if vignette and (len(vignette) > 2000 or not _MOTIF_URL.match(vignette)):
        vignette = None
    _verifier_profil(client, user_id, profil_id)
    try:
        existante = _garde_existante(client, user_id, profil_id, adresse)
        if existante:
            return existante
        try:
            lignes = (
                client.table("bambara_gardes")
                .insert(
                    {
                        "user_id": user_id,
                        "profil_id": profil_id or None,
                        "genre": genre,
                        "url": adresse,
                        "titre": (titre or "").strip()[:300],
                        "miniature": vignette,
                        "id_video": ((id_video or "").strip()[:64] or None),
                    }
                )
                .execute()
                .data
            )
        except Exception:
            # Deux demandes en même temps pour le même élément : l'une a gagné, on renvoie sa ligne.
            existante = _garde_existante(client, user_id, profil_id, adresse)
            if existante:
                return existante
            raise
    except Exception as e:
        logging.error("ERREUR SUPABASE (garder bambara pour %s) : %s", user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    if not lignes:
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    ligne = lignes[0]
    return {k: ligne.get(k) for k in ("id", "genre", "url", "titre", "miniature", "id_video", "cree_a")}


def retirer_garde(client, user_id, garde_id) -> None:
    identifiant = _identifiant(garde_id, "BAMBARA_GARDE_INVALIDE")
    try:
        client.table("bambara_gardes").delete().eq("id", identifiant).eq("user_id", user_id).execute()
    except Exception as e:
        logging.error("ERREUR SUPABASE (retrait gardé bambara %s pour %s) : %s", identifiant, user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
