-- 13/09/2026, demande Bourama : les valeurs d'un dossier (pays, niveau,
-- categorie, classe, specialite -- voir migration
-- 2026_09_13_filtres_dossiers_catalogue_public_multi.sql) peuvent en
-- plus descendre automatiquement à tous ses descendants (sous-dossiers
-- ET fichiers, à n'importe quelle profondeur), de façon additive
-- (jamais de remplacement des valeurs propres d'un descendant).
--
-- Pour chaque valeur d'un filtre, on choisit séparément si elle
-- descend aux sous-dossiers, aux fichiers, aux deux, ou à aucun des
-- deux -- d'où 2 nouvelles colonnes par filtre (10 au total), chacune
-- un SOUS-ENSEMBLE de la colonne de base correspondante.
--
-- Ne concerne QUE dossiers_catalogue_public -- un fichier ne "propage"
-- rien lui-même, il ne fait qu'hériter.

alter table dossiers_catalogue_public add column if not exists pays_heritage_sous_dossiers text[] default array[]::text[];
alter table dossiers_catalogue_public add column if not exists pays_heritage_fichiers text[] default array[]::text[];
alter table dossiers_catalogue_public add column if not exists niveau_heritage_sous_dossiers text[] default array[]::text[];
alter table dossiers_catalogue_public add column if not exists niveau_heritage_fichiers text[] default array[]::text[];
alter table dossiers_catalogue_public add column if not exists categorie_heritage_sous_dossiers text[] default array[]::text[];
alter table dossiers_catalogue_public add column if not exists categorie_heritage_fichiers text[] default array[]::text[];
alter table dossiers_catalogue_public add column if not exists classe_heritage_sous_dossiers text[] default array[]::text[];
alter table dossiers_catalogue_public add column if not exists classe_heritage_fichiers text[] default array[]::text[];
alter table dossiers_catalogue_public add column if not exists specialite_heritage_sous_dossiers text[] default array[]::text[];
alter table dossiers_catalogue_public add column if not exists specialite_heritage_fichiers text[] default array[]::text[];
