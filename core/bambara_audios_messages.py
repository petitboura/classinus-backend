"""Page bambara : tous les messages audio d'une conversation (22/11/2026, demande de Bourama).

Table bambara_audios_messages (migration 2026_11_22_bambara_audios_messages.sql). Chaque voix, celle de la
personne (« question ») comme celle de Classinus (« reponse »), est gardée et rattachée au message écrit
correspondant de historique_conversations. En rouvrant une conversation de l'historique, la page relit la
liste légère des audios puis chaque son à la demande.

Les erreurs sont les codes stables de core/bambara_profils.py (traduits dans core/erreurs.py).
"""
import base64
import binascii
import logging

from core.bambara_profils import LONGUEUR_MAX_AUDIO_BASE64, ErreurBambara, _identifiant

SENS_AUDIO = {"question": "user", "reponse": "assistant"}
MAX_AUDIOS_PAR_CONVERSATION = 200


def _message_du_compte(client, user_id, conversation_id, message_id, sens) -> bool:
    """Le message existe, appartient à ce compte, est dans cette conversation et a le bon rôle."""
    try:
        lignes = (
            client.table("historique_conversations")
            .select("id")
            .eq("id", message_id)
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .eq("role", SENS_AUDIO[sens])
            .limit(1)
            .execute()
            .data
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (vérification message bambara %s pour %s) : %s", message_id, user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    return bool(lignes)


def _audio_deja_la(client, user_id, message_id, sens) -> bool:
    lignes = (
        client.table("bambara_audios_messages")
        .select("id")
        .eq("user_id", user_id)
        .eq("message_id", message_id)
        .eq("sens", sens)
        .limit(1)
        .execute()
        .data
    )
    return bool(lignes)


def enregistrer_audio_message(client, user_id, conversation_id, message_id, sens, audio) -> dict:
    """Garde le son d'un message. Le renvoyer une seconde fois ne change rien.

    `audio` est un dict {base64, duree_ms, pics}."""
    identifiant = _identifiant(conversation_id, "BAMBARA_CONVERSATION_INVALIDE")
    if sens not in SENS_AUDIO:
        raise ErreurBambara("BAMBARA_AUDIO_INVALIDE")
    try:
        numero = int(message_id)
    except (TypeError, ValueError):
        raise ErreurBambara("BAMBARA_AUDIO_INVALIDE")
    brut = (audio or {}).get("base64") or ""
    if not brut or len(brut) > LONGUEUR_MAX_AUDIO_BASE64:
        raise ErreurBambara("BAMBARA_AUDIO_INVALIDE")
    try:
        base64.b64decode(brut, validate=True)
    except (binascii.Error, ValueError):
        raise ErreurBambara("BAMBARA_AUDIO_INVALIDE")
    if not _message_du_compte(client, user_id, identifiant, numero, sens):
        raise ErreurBambara("BAMBARA_CONVERSATION_INTROUVABLE")
    try:
        if _audio_deja_la(client, user_id, numero, sens):
            return {"deja_enregistre": True}
        total = (
            client.table("bambara_audios_messages")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("conversation_id", identifiant)
            .limit(1)
            .execute()
            .count
        )
        if (total or 0) >= MAX_AUDIOS_PAR_CONVERSATION:
            raise ErreurBambara("BAMBARA_AUDIO_INVALIDE")
        try:
            client.table("bambara_audios_messages").insert(
                {
                    "user_id": user_id,
                    "conversation_id": identifiant,
                    "message_id": numero,
                    "sens": sens,
                    "audio_base64": brut,
                    "duree_ms": max(0, int((audio or {}).get("duree_ms") or 0)),
                    "pics": [round(float(p), 3) for p in ((audio or {}).get("pics") or [])][:64],
                }
            ).execute()
        except Exception:
            # Deux envois en même temps pour le même message : l'un a gagné, c'est bon.
            if _audio_deja_la(client, user_id, numero, sens):
                return {"deja_enregistre": True}
            raise
    except ErreurBambara:
        raise
    except Exception as e:
        logging.error("ERREUR SUPABASE (audio message bambara %s pour %s) : %s", numero, user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    return {"deja_enregistre": False}


def lister_audios_conversation(client, user_id, conversation_id) -> list:
    """La liste légère des sons d'une conversation (sans le son lui-même), dans l'ordre des messages."""
    identifiant = _identifiant(conversation_id, "BAMBARA_CONVERSATION_INVALIDE")
    try:
        return (
            client.table("bambara_audios_messages")
            .select("id,message_id,sens,duree_ms")
            .eq("user_id", user_id)
            .eq("conversation_id", identifiant)
            .order("message_id")
            .limit(MAX_AUDIOS_PAR_CONVERSATION)
            .execute()
            .data
            or []
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (liste audios bambara %s pour %s) : %s", identifiant, user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")


def lire_audio_message(client, user_id, audio_id) -> dict:
    """Le son d'un message du compte : base64, durée et hauteurs des barres."""
    identifiant = _identifiant(audio_id, "BAMBARA_CONVERSATION_INVALIDE")
    try:
        lignes = (
            client.table("bambara_audios_messages")
            .select("audio_base64,duree_ms,pics")
            .eq("id", identifiant)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
        )
    except Exception as e:
        logging.error("ERREUR SUPABASE (lecture audio message bambara %s pour %s) : %s", identifiant, user_id, e)
        raise ErreurBambara("BAMBARA_INDISPONIBLE")
    if not lignes:
        raise ErreurBambara("BAMBARA_CONVERSATION_INTROUVABLE")
    ligne = lignes[0]
    return {"base64": ligne["audio_base64"], "duree_ms": ligne["duree_ms"], "pics": ligne.get("pics") or []}
