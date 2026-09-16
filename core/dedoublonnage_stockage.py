"""
Déduplication du stockage Supabase pour le bucket "bibliotheque",
partagé par les 3 bibliothèques (privée : fichiers_uploades, publique :
bibliotheque_publique, dossiers désignés : fichiers_dossier_designe).

Ajouté le 16/09/2026, demande Bourama (chantier quota Supabase dépassé) :
avant, chaque ajout re-uploadait les octets du fichier comme un objet
Storage tout neuf, même si un fichier au contenu strictement identique
existait déjà quelque part dans le bucket -- un même PDF ajouté par 6
personnes différentes finissait stocké 6 fois. Portée volontairement
limitée aux FUTURS ajouts (Bourama a confirmé ne pas vouloir traiter les
doublons déjà existants, qui ne seront de toute façon pas repris lors
d'une future migration de base de données).

Principe : seul l'OBJET STORAGE (les octets) est partagé entre
plusieurs lignes de metadonnées -- chaque ligne (fichiers_uploades,
bibliotheque_publique, fichiers_dossier_designe) garde sa propre
existence, son propriétaire, son statut de vectorisation, etc.
totalement indépendants ; seul `chemin_stockage` peut pointer vers le
même objet que celui d'une autre ligne. Un objet n'est physiquement
supprimé du Storage qu'au moment où PLUS AUCUNE ligne (dans aucune des
3 tables) ne le référence -- sinon on casserait l'accès de quelqu'un
d'autre qui partage le même fichier.
"""

import hashlib
import logging
import uuid

BUCKET = "bibliotheque"

# Les 3 tables qui peuvent référencer un chemin_stockage de ce bucket.
_TABLES_BUCKET_BIBLIOTHEQUE = ("fichiers_uploades", "bibliotheque_publique", "fichiers_dossier_designe")


def calculer_hash(contenu: bytes) -> str:
    return hashlib.sha256(contenu).hexdigest()


def _trouver_chemin_existant(supabase, hash_contenu: str) -> str | None:
    for table in _TABLES_BUCKET_BIBLIOTHEQUE:
        try:
            res = (
                supabase.table(table)
                .select("chemin_stockage")
                .eq("hash_contenu", hash_contenu)
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0]["chemin_stockage"]
        except Exception as e:
            logging.error(f"ERREUR recherche doublon (table {table}, hash {hash_contenu[:12]}...) : {e}")
    return None


def stocker_avec_dedoublonnage(supabase, contenu: bytes, extension: str, niveau_dossier: str, type_mime: str) -> tuple[str, str]:
    """
    Renvoie (chemin_stockage, hash_contenu) à écrire dans la ligne de
    metadonnées de l'appelant. Si un fichier identique existe déjà dans
    le bucket (n'importe laquelle des 3 bibliothèques), réutilise son
    chemin_stockage SANS réuploader -- sinon, upload normalement sous un
    nouveau chemin. `niveau_dossier` = le même préfixe de dossier que
    l'appelant utilisait déjà (ex. "utilisateur", "agent", "plateforme",
    "publique", "dossiers_designes") -- uniquement utilisé pour le
    chemin d'un NOUVEL upload, sans effet sur un fichier réutilisé.
    """
    hash_contenu = calculer_hash(contenu)
    chemin_existant = _trouver_chemin_existant(supabase, hash_contenu)
    if chemin_existant:
        return chemin_existant, hash_contenu

    chemin_stockage = f"{niveau_dossier}/{uuid.uuid4()}.{extension}"
    supabase.storage.from_(BUCKET).upload(chemin_stockage, contenu, {"content-type": type_mime})
    return chemin_stockage, hash_contenu


def supprimer_stockage_si_dernier_usage(supabase, chemin_stockage: str) -> None:
    """
    À appeler APRÈS avoir supprimé la ligne de metadonnées (dans
    n'importe laquelle des 3 tables). Si plus aucune ligne (dans aucune
    des 3 tables) ne référence encore ce chemin_stockage, supprime aussi
    l'objet physique du Storage -- sinon le laisse en place (quelqu'un
    d'autre l'utilise encore).
    """
    for table in _TABLES_BUCKET_BIBLIOTHEQUE:
        try:
            res = (
                supabase.table(table)
                .select("id")
                .eq("chemin_stockage", chemin_stockage)
                .limit(1)
                .execute()
            )
            if res.data:
                return  # encore référencé ailleurs, on ne touche pas au fichier physique
        except Exception as e:
            logging.error(f"ERREUR vérification usage restant avant suppression (table {table}, chemin {chemin_stockage}) : {e}")
            return  # par prudence, on ne supprime rien si on n'a pas pu vérifier partout

    try:
        supabase.storage.from_(BUCKET).remove([chemin_stockage])
    except Exception as e:
        logging.error(f"ERREUR suppression Storage (chemin {chemin_stockage}) : {e}")
