"""
Mémoire élève persistante et incrémentale (chantier 27/09/2026, demande
Bourama). C'est l'unique système de mémoire de l'élève : l'ancien
système (résumé automatique et outil gerer_memoire_utilisateur, table
conversation_summaries) a été retiré.

L'ancien système stockait tout dans un unique JSON par élève, fusion
au premier niveau seulement (dict.update) : une mise à jour sur une clé
de premier niveau déjà utilisée écrasait tout son contenu imbriqué au
lieu de le compléter, symptôme rapporté par Bourama d'une mémoire qui
"change" au lieu de s'accumuler. Nouveau principe ici : une ligne par
(élève, catégorie, sous_categorie) dans memoire_eleve (voir
migrations/2026_09_27_memoire_eleve.sql), jamais de réécriture globale ,
une écriture ne touche jamais que sa propre ligne.

Catégories de premier niveau imposées (CATEGORIES_MEMOIRE_ELEVE) : le
modèle ne peut pas en créer d'autres à ce niveau. Sous-catégories
libres, décidées par le modèle selon chaque élève.

Ce module ne connaît rien du protocole MCP (voir
core/outils_memoire_eleve.py pour les outils appelés par le modèle) ,
seulement l'accès Supabase, même découpage que
core/historique_reponses_qcm.py / core/outils_reponses_qcm.py.
"""

import logging
from datetime import datetime, timezone

from core.outils_generation_commun import _supabase_memoire

CATEGORIES_MEMOIRE_ELEVE: tuple[str, ...] = ("identite", "scolarite", "apprentissage", "preferences")

_TABLE = "memoire_eleve"

# Chaîne vide, jamais NULL, pour représenter "pas de sous-catégorie"
# (ligne racine d'une catégorie) : deux NULL ne sont jamais égaux pour une
# contrainte unique Postgres, ce qui casserait à la fois l'unicité
# (user_id, categorie, sous_categorie) et l'upsert on_conflict ci-dessous
# si on utilisait NULL. Converti en None uniquement à la sortie vers
# l'appelant (voir _vers_api/_depuis_api).
_RACINE = ""


def _depuis_api(sous_categorie: str | None) -> str:
    return sous_categorie if sous_categorie else _RACINE


def _vers_api(sous_categorie: str) -> str | None:
    return sous_categorie or None


def obtenir_sommaire(user_id: str) -> list[dict]:
    """
    Une entrée par catégorie/sous-catégorie déjà connue pour cet élève :
    categorie, sous_categorie, description, updated_at, JAMAIS le
    contenu (voir lire_categorie pour ça, à n'appeler que sur la ligne
    précise identifiée ici). Les catégories du socle sans aucune ligne
    existante sont quand même incluses, description=None, pour que le
    modèle sache où ranger un premier fait sans en inventer une nouvelle.
    Liste vide en cas d'erreur Supabase, jamais d'exception vers
    l'appelant (même convention que historique_reponses_qcm.py).
    """
    try:
        lignes = (
            _supabase_memoire.table(_TABLE)
            .select("categorie, sous_categorie, description, updated_at")
            .eq("user_id", user_id)
            .execute()
        ).data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (sommaire memoire_eleve, user {user_id}) : {e}")
        return []

    for ligne in lignes:
        ligne["sous_categorie"] = _vers_api(ligne["sous_categorie"])

    racines_existantes = {l["categorie"] for l in lignes if l["sous_categorie"] is None}
    for categorie in CATEGORIES_MEMOIRE_ELEVE:
        if categorie not in racines_existantes:
            lignes.append({"categorie": categorie, "sous_categorie": None, "description": None, "updated_at": None})

    lignes.sort(key=lambda l: (l["categorie"], l["sous_categorie"] or ""))
    return lignes


def lire_categorie(user_id: str, categorie: str, sous_categorie: str | None = None) -> dict | None:
    """
    Contenu complet d'UNE seule ligne (categorie/sous_categorie) pour cet
    élève. None si elle n'existe pas encore, ou en cas d'erreur Supabase
    (jamais d'exception vers l'appelant).
    """
    try:
        res = (
            _supabase_memoire.table(_TABLE)
            .select("contenu, description, updated_at")
            .eq("user_id", user_id)
            .eq("categorie", categorie)
            .eq("sous_categorie", _depuis_api(sous_categorie))
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture memoire_eleve, user {user_id}, {categorie}/{sous_categorie}) : {e}")
        return None
    # maybe_single().execute() renvoie None (pas un objet vide) quand la ligne
    # n'existe pas, comme partout ailleurs dans le depot : tester res avant res.data.
    if not res or not res.data:
        return None
    return res.data


def ecrire_categorie(
    user_id: str,
    categorie: str,
    sous_categorie: str | None,
    contenu: dict,
    description: str,
) -> tuple[bool, str | None]:
    """
    Crée ou remplace le contenu d'UNE SEULE ligne (categorie/sous_categorie),
    jamais les autres lignes de cet élève, c'est tout le principe de
    cette refonte (voir docstring de module). `categorie` doit faire
    partie du socle (CATEGORIES_MEMOIRE_ELEVE), sinon l'écriture est
    refusée AVANT tout appel Supabase (pas de garde-fou côté base, la
    contrainte SQL check refuserait aussi mais avec une erreur moins
    claire pour l'appelant).

    Renvoie (succes, message_erreur). message_erreur est None en cas de
    succès, sinon un texte prêt à être renvoyé tel quel par l'outil MCP
    appelant.
    """
    if categorie not in CATEGORIES_MEMOIRE_ELEVE:
        return False, (
            f"Erreur : categorie '{categorie}' invalide. Catégories possibles : "
            f"{', '.join(CATEGORIES_MEMOIRE_ELEVE)}."
        )
    ligne = {
        "user_id": user_id,
        "categorie": categorie,
        "sous_categorie": _depuis_api(sous_categorie),
        "contenu": contenu,
        "description": description,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _supabase_memoire.table(_TABLE).upsert(
            ligne, on_conflict="user_id,categorie,sous_categorie"
        ).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (écriture memoire_eleve, user {user_id}, {categorie}/{sous_categorie}) : {e}")
        return False, "Erreur : l'écriture en mémoire a échoué, réessaie."
    return True, None
