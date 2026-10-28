-- Palier root Class-Tech DESACTIVE (28/10/2026, demande Bourama via
-- builder root) : declare les 19 outils root du serveur diagnostic
-- comme NON disponibles cote plateforme. Memes colonnes que la ligne
-- serveur (2026_10_28_serveur_diagnostic_classtech.sql, categorie 2 =
-- serveur public) : ces lignes documentent l'etat voulu outil par outil.
-- Les outils root ne sont NI dans CATEGORIES_OUTILS["diagnostic_classtech"]
-- (la recherche par categorie ne les propose pas) NI deployes (branche
-- outils-root non fusionnee) : triple protection jusqu'a l'ordre de Bourama.
-- Tous sont aussi dans OUTILS_SENSIBLES (confirmation exigee).
-- Pour ACTIVER (sur ordre de Bourama uniquement) : passer chaque ligne a
-- disponible = true, ajouter les noms a la categorie diagnostic_classtech
-- dans core/registre_outils.py, fusionner et deployer. Le cache des outils
-- dure 24h : redeployer le backend (ou forcer le rechargement du catalogue)
-- pour que le changement soit visible sans attendre.

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at) values
('root_verifier_acces', 2, 'diagnostic_classtech', false, now()),
('root_lire_infos_root', 2, 'diagnostic_classtech', false, now()),
('root_lister_fichiers_systeme', 2, 'diagnostic_classtech', false, now()),
('root_lire_fichier_systeme', 2, 'diagnostic_classtech', false, now()),
('root_lire_erreurs_noyau', 2, 'diagnostic_classtech', false, now()),
('root_lire_paniques_passees', 2, 'diagnostic_classtech', false, now()),
('root_lire_partitions', 2, 'diagnostic_classtech', false, now()),
('root_verifier_integrite', 2, 'diagnostic_classtech', false, now()),
('root_lire_batterie_brute', 2, 'diagnostic_classtech', false, now()),
('root_lire_temperatures', 2, 'diagnostic_classtech', false, now()),
('root_reinitialiser_stats_batterie', 2, 'diagnostic_classtech', false, now()),
('root_lire_firmware', 2, 'diagnostic_classtech', false, now()),
('root_valider_slot_demarre', 2, 'diagnostic_classtech', false, now()),
('root_lister_processus', 2, 'diagnostic_classtech', false, now()),
('root_lire_wakelocks', 2, 'diagnostic_classtech', false, now()),
('root_nettoyer_fichiers_crash', 2, 'diagnostic_classtech', false, now()),
('root_vider_cache_dalvik', 2, 'diagnostic_classtech', false, now()),
('root_forcer_trim', 2, 'diagnostic_classtech', false, now()),
('root_redemarrer', 2, 'diagnostic_classtech', false, now())
on conflict (nom_outil) do update set disponible = false, updated_at = now();
