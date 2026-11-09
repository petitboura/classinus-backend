"""Crédits d'images : chaque image générée avec Higgsfield coûte 1 crédit.

Le solde vit en base (table credits_images). Le retrait, le remboursement et la création de
la ligne d'un nouveau compte sont faits par des fonctions SQL atomiques (migration
2026_11_09_credits_images_fonctions.sql) : deux demandes en même temps ne peuvent pas faire
passer le solde sous zéro, et un crédit n'est rendu qu'une seule fois.

Le solde de départ et le gain par filleul se règlent dans la table parrainage_reglages,
sans toucher au code. Seules les images sont concernées, la vidéo n'est pas touchée.

Déroulé pour une génération :
1. reserver_credit_image : retire 1 crédit juste avant l'envoi à Higgsfield (refus à 0).
2. Si l'envoi échoue tout de suite : rendre_credit_image avec la même référence.
3. Si l'envoi réussit : rattacher_credit_image remplace la référence provisoire par
   l'identifiant de la génération, pour qu'un échec constaté plus tard (suivi serveur)
   puisse rendre le crédit.
"""
import logging
import uuid

from core.higgsfield_requetes import ErreurHiggsfield


class ErreurCreditsImages(ErreurHiggsfield):
    """Erreur destinée à l'utilisateur : un code stable, traduit en français et en anglais dans
    core/erreurs.py (et lib/erreurs.ts côté frontend), jamais un texte écrit en dur ici."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# Texte donné à l'IA du chat quand une image est refusée. L'IA le reformule pour la personne,
# dans sa langue. Aucun chiffre ici : le gain par filleul se règle en base.
_MESSAGES_IA = {
    "CREDITS_IMAGES_EPUISES": (
        "Erreur : l'utilisateur n'a plus de crédits d'images. Dis-le lui clairement, sans relancer "
        "la génération, et explique qu'il peut en gagner d'autres en invitant ses amis : chaque ami "
        "qui s'inscrit lui rapporte des crédits d'images."
    ),
    "CREDITS_IMAGES_INDISPONIBLE": (
        "Erreur : impossible de vérifier le solde de crédits d'images pour le moment. "
        "Dis-le à l'utilisateur et propose de réessayer dans un instant."
    ),
}


def message_pour_ia(erreur: ErreurCreditsImages) -> str:
    return _MESSAGES_IA.get(erreur.code, _MESSAGES_IA["CREDITS_IMAGES_INDISPONIBLE"])


def reserver_credit_image(client_base, user_id) -> str:
    """Retire 1 crédit et renvoie la référence provisoire à garder pour rembourser ou rattacher.

    À appeler juste avant l'envoi à Higgsfield. Sans utilisateur identifié, on refuse : aucun
    crédit ne pourrait être retiré. Si la base ne répond pas, on refuse aussi (jamais d'image gratuite
    par défaut).
    """
    if not user_id:
        raise ErreurHiggsfield("Impossible d'identifier l'utilisateur, génération refusée.")
    reference = uuid.uuid4().hex
    try:
        reponse = client_base.rpc(
            "credits_images_reserver", {"p_user": user_id, "p_reference": reference}
        ).execute()
    except Exception as e:
        logging.error("ERREUR SUPABASE (retrait crédit image pour %s) : %s", user_id, e)
        raise ErreurCreditsImages("CREDITS_IMAGES_INDISPONIBLE")
    if reponse.data is not True:
        raise ErreurCreditsImages("CREDITS_IMAGES_EPUISES")
    return reference


def rendre_credit_image(client_base, user_id, reference) -> None:
    """Rend le crédit d'une génération qui n'a pas abouti. Ne lève jamais et ne rend qu'une fois."""
    if not user_id or not reference:
        return
    try:
        client_base.rpc("credits_images_rendre", {"p_user": user_id, "p_reference": reference}).execute()
    except Exception as e:
        logging.error("ERREUR SUPABASE (remboursement crédit image %s, user %s) : %s", reference, user_id, e)


def rattacher_credit_image(client_base, user_id, reference, request_id) -> None:
    """Associe le crédit retiré à la génération lancée. Ne lève jamais : la génération est déjà partie."""
    if not user_id or not reference or not request_id:
        return
    try:
        client_base.rpc(
            "credits_images_rattacher",
            {"p_user": user_id, "p_ancienne": reference, "p_nouvelle": request_id},
        ).execute()
    except Exception as e:
        logging.error("ERREUR SUPABASE (rattachement crédit image %s à %s, user %s) : %s", reference, request_id, user_id, e)
