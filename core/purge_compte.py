"""
Purge des données d'un compte à sa suppression (hors conversations, agents,
mémoire de l'élève, publications et profil, déjà gérés par
api/profiles.py:supprimer_mon_compte).

Ajouté le 12/10/2026, demande de Bourama : Google Play et la loi tunisienne
2004-63 demandent que la suppression d'un compte supprime aussi les données
qui lui sont liées. L'audit du schéma réel de la base a montré que presque
aucune table n'est liée au compte par une clé étrangère avec suppression en
cascade : sans cette purge, bibliothèque, connexions Notion et Google, temps
d'écran, rappels, réponses aux QCM, etc. restaient en base.

Ce qui est volontairement GARDÉ : le journal des actions (journal_actions),
pour la sécurité. Sa colonne user_id passe à NULL à la suppression du compte
(ON DELETE SET NULL), la ligne "compte.supprime" garde l'e-mail.

Chaque étape est best-effort (log et continue) : une table en erreur ne doit
pas empêcher la suppression du reste ni du compte. Les erreurs sont loguées
avec le nom de la table pour pouvoir être reprises à la main.
"""

import logging

from core import stockage_r2
from core.dedoublonnage_stockage import supprimer_stockage_si_dernier_usage


# Tables dont une colonne désigne le compte, sans suppression en cascade.
# Les tables enfants de celles-ci partent seules (ON DELETE CASCADE vérifié
# dans le schéma le 12/10/2026) : documents_bibliotheque via fichiers_uploades,
# fichiers_dossiers_bibliotheque et miroirs via dossiers_bibliotheque,
# rattachements_codes, notions et partages via codes_partage,
# activations via comportements_publics, notions_catalogue_public via
# programmes_catalogue_public.
_TABLES_SIMPLES = (
    # Connexions à des services extérieurs (jetons Notion et Google).
    ("connexions_notion", "user_id"),
    ("connexions_oauth", "user_id"),
    ("notion_oauth_temp", "user_id"),
    ("oauth_temp", "user_id"),
    ("higgsfield_oauth_connections", "user_id"),
    ("higgsfield_oauth_temp", "user_id"),
    ("platform_mcp_oauth_connections", "user_id"),
    ("platform_mcp_oauth_temp", "user_id"),
    # Appareil : temps d'écran, actions, jetons de notifications, rappels.
    ("usage_appareil_mobile", "user_id"),
    ("actions_appareil_mobile", "user_id"),
    ("abonnements_push", "user_id"),
    ("appareils_mobiles_push_tokens", "user_id"),
    ("rappels", "user_id"),
    ("minuteurs", "user_id"),
    ("relances_proactives", "user_id"),
    # Réglages et réponses liés aux conversations de l'élève.
    ("historique_reponses_qcm", "user_id"),
    ("feedback_messages", "user_id"),
    ("conversation_mode_actif", "user_id"),
    ("conversation_mode_source", "user_id"),
    ("conversation_persona_pedagogique", "user_id"),
    ("conversation_guide_actif", "user_id"),
    ("agent_user_profiles", "user_id"),
    ("agents_administrateurs", "user_id"),
    ("rattachements_par_matiere", "etudiant_id"),
    # Bibliothèque : lignes de métadonnées (les fichiers physiques sont
    # traités avant, voir _purger_fichiers).
    ("documents_bibliotheque", "user_id"),
    ("documents_dossier_designe", "user_id"),
    ("dossiers_publics_attaches", "user_id"),
    ("dossiers_designes_mobile", "user_id"),
    ("dossiers_bibliotheque", "user_id"),
    # Messages directs, dans les deux sens.
    ("messages_directs", "expediteur_id"),
    ("messages_directs", "destinataire_id"),
    # Contenu partagé ou publié par le compte (décision de Bourama du
    # 12/10/2026 : tout supprimer, sinon il reste attaché à un compte supprimé).
    ("codes_partage", "proprietaire_id"),
    ("comportements_publics", "auteur_id"),
    ("programmes_catalogue_public", "publie_par"),
    ("demandes_dossiers_catalogue_public", "createur_id"),
    # Signalements pédagogiques où le compte est l'élève.
    ("signalements", "etudiant_id"),
)


def _supprimer(supabase, table: str, colonne: str, user_id: str) -> None:
    try:
        supabase.table(table).delete().eq(colonne, user_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (purge compte, table {table}.{colonne} pour {user_id}) : {e}")


def _purger_fichiers(supabase, user_id: str) -> None:
    """
    Supprime les fichiers de la bibliothèque du compte : lignes de
    métadonnées PUIS objets physiques. Les lignes sont supprimées avant le
    stockage parce que supprimer_stockage_si_dernier_usage ne supprime
    l'objet que si plus aucune ligne ne le référence (un même objet peut être
    partagé entre plusieurs comptes grâce à la déduplication).
    """
    chemins = set()
    for table, colonne in (
        ("fichiers_uploades", "user_id"),
        ("fichiers_dossier_designe", "user_id"),
        ("bibliotheque_publique", "ajoute_par"),
    ):
        try:
            res = supabase.table(table).select("chemin_stockage").eq(colonne, user_id).execute()
            for ligne in res.data or []:
                if ligne.get("chemin_stockage"):
                    chemins.add(ligne["chemin_stockage"])
        except Exception as e:
            logging.error(f"ERREUR SUPABASE (purge compte, lecture chemins {table} pour {user_id}) : {e}")
            continue
        _supprimer(supabase, table, colonne, user_id)

    for chemin in chemins:
        try:
            supprimer_stockage_si_dernier_usage(supabase, chemin)
        except Exception as e:
            logging.error(f"ERREUR purge compte (stockage {chemin} pour {user_id}) : {e}")


def _detacher_etablissements(supabase, user_id: str) -> None:
    """
    Quatre liens vers le compte n'ont PAS de suppression en cascade et
    faisaient échouer la suppression (erreur PROFIL_FERMETURE_PARTIELLE) pour
    un compte qui avait publié un programme, géré un établissement ou
    enseigné à d'autres comptes.
    """
    for table, colonne in (
        ("etablissements_rattachements", "utilisateur_id"),
        ("etablissements_publications", "auteur_id"),
        ("annonces_etablissement", "etablissement_id"),
        ("etablissements", "profile_id"),
    ):
        _supprimer(supabase, table, colonne, user_id)

    # Colonnes qui peuvent rester vides : on retire seulement la référence.
    for table, colonne in (
        ("etablissements_publications", "valide_par"),
        ("profiles", "enseignant_id"),
        ("profiles", "etablissement_id"),
        ("signalements", "prof_id"),
    ):
        try:
            supabase.table(table).update({colonne: None}).eq(colonne, user_id).execute()
        except Exception as e:
            logging.error(f"ERREUR SUPABASE (purge compte, détachement {table}.{colonne} pour {user_id}) : {e}")


def purger_donnees_compte(supabase, user_id: str) -> None:
    """Point d'entrée, à appeler avant la suppression du profil."""
    _detacher_etablissements(supabase, user_id)
    # Les objets R2 des skills sont indépendants des lignes Supabase.
    try:
        ids = [row["id"] for row in (supabase.table("skills").select("id").eq("owner_id", user_id).execute().data or [])]
        if ids:
            rows = supabase.table("skill_files").select("cle_stockage").in_("skill_id", ids).execute().data or []
            for row in rows:
                try:
                    stockage_r2.from_("skills").remove([row["cle_stockage"]])
                except Exception as e:
                    logging.error(f"ERREUR purge compte (fichier skill R2 {user_id}) : {e}")
            supabase.table("skills").delete().eq("owner_id", user_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (purge skills {user_id}) : {e}")
    _purger_fichiers(supabase, user_id)

    # Les activations de skills publics pointent vers le comportement de
    # l'élève avec SET NULL : on les supprime avant, pour ne pas laisser de
    # lignes orphelines.
    try:
        ids = supabase.table("comportements_etudiants").select("id").eq("etudiant_id", user_id).execute()
        liste = [ligne["id"] for ligne in (ids.data or [])]
        if liste:
            supabase.table("comportement_public_activations").delete().in_("comportement_etudiant_id", liste).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (purge compte, activations de skills pour {user_id}) : {e}")
    _supprimer(supabase, "comportements_etudiants", "etudiant_id", user_id)

    for table, colonne in _TABLES_SIMPLES:
        _supprimer(supabase, table, colonne, user_id)
