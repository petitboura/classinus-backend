-- 15/09/2026, demande Bourama : un FICHIER du catalogue public doit
-- désormais pouvoir avoir PLUSIEURS valeurs pour chacun de ses 5
-- filtres (pays, niveau, categorie, classe, specialite), même principe
-- que ce qui a déjà été fait pour les dossiers le 13/09/2026 (voir
-- 2026_09_13_filtres_dossiers_catalogue_public_multi.sql). Jusqu'ici un
-- fichier gardait volontairement une seule valeur par filtre pendant
-- que le chantier dossiers avançait, mais ce chantier n'est plus
-- "temporaire" : il termine l'alignement fichier/dossier.
--
-- Chaque colonne text -> text[] sur bibliotheque_publique UNIQUEMENT.
-- La table dossiers_catalogue_public n'est pas concernée ici (déjà
-- migrée le 13/09/2026).
--
-- Conversion sans perte : une valeur existante 'Mali' devient ['Mali'],
-- une valeur vide/NULL devient un tableau vide.
--
-- La vue vue_catalogue_public_fichiers (créée le 13/09/2026) dépend de
-- ces colonnes : obligée de la supprimer puis la recréer à l'identique
-- autour de l'altération (Postgres refuse d'altérer le type d'une
-- colonne utilisée par une vue).

drop view if exists vue_catalogue_public_fichiers;

alter table bibliotheque_publique
  alter column pays type text[] using (case when pays is null or pays = '' then array[]::text[] else array[pays] end);

alter table bibliotheque_publique
  alter column niveau type text[] using (case when niveau is null or niveau = '' then array[]::text[] else array[niveau] end);

alter table bibliotheque_publique
  alter column categorie type text[] using (case when categorie is null or categorie = '' then array[]::text[] else array[categorie] end);

alter table bibliotheque_publique
  alter column classe type text[] using (case when classe is null or classe = '' then array[]::text[] else array[classe] end);

alter table bibliotheque_publique
  alter column specialite type text[] using (case when specialite is null or specialite = '' then array[]::text[] else array[specialite] end);

alter table bibliotheque_publique alter column pays set default array[]::text[];
alter table bibliotheque_publique alter column niveau set default array[]::text[];
alter table bibliotheque_publique alter column categorie set default array[]::text[];
alter table bibliotheque_publique alter column classe set default array[]::text[];
alter table bibliotheque_publique alter column specialite set default array[]::text[];

-- Mêmes raisons que pour les dossiers : les anciens index simples ne
-- sont plus utiles sur un tableau (une recherche "contient cette
-- valeur" a besoin d'un index GIN, pas b-tree).
drop index if exists idx_bibliotheque_publique_pays;
drop index if exists idx_bibliotheque_publique_niveau;
drop index if exists idx_bibliotheque_publique_categorie;

create index if not exists idx_bibliotheque_publique_pays_gin on bibliotheque_publique using gin (pays);
create index if not exists idx_bibliotheque_publique_niveau_gin on bibliotheque_publique using gin (niveau);
create index if not exists idx_bibliotheque_publique_categorie_gin on bibliotheque_publique using gin (categorie);
create index if not exists idx_bibliotheque_publique_classe_gin on bibliotheque_publique using gin (classe);
create index if not exists idx_bibliotheque_publique_specialite_gin on bibliotheque_publique using gin (specialite);

create view vue_catalogue_public_fichiers as
 SELECT b.id AS fichier_id,
    b.nom,
    b.nom_fichier,
    b.type_mime,
    b.statut,
    b.retire_motif,
    b.retire_le,
    b.statut_vectorisation AS statut_vectorisation_declare,
    COALESCE(v.nb_chunks, 0::bigint) AS nb_chunks,
    COALESCE(v.nb_chunks, 0::bigint) > 0 AS vectorise_reellement,
        CASE
            WHEN b.statut_vectorisation = 'pret'::text AND COALESCE(v.nb_chunks, 0::bigint) = 0 THEN 'declare_pret_mais_aucun_chunk'::text
            WHEN b.statut_vectorisation = 'echec'::text AND COALESCE(v.nb_chunks, 0::bigint) > 0 THEN 'declare_echec_mais_chunks_presents'::text
            ELSE NULL::text
        END AS anomalie_vectorisation,
    b.tentatives_vectorisation,
    b.erreur_vectorisation,
    b.derniere_tentative_vectorisation_a,
    b.statut_extraction_texte,
    b.pays,
    b.niveau,
    b.categorie,
    b.classe,
    b.specialite,
    COALESCE(d.dossiers, '[]'::jsonb) AS dossiers,
    b.created_at
   FROM bibliotheque_publique b
     LEFT JOIN ( SELECT documents_catalogue_public.fichier_id,
            count(*) AS nb_chunks
           FROM documents_catalogue_public
          GROUP BY documents_catalogue_public.fichier_id) v ON v.fichier_id = b.id
     LEFT JOIN ( SELECT fd.fichier_id,
            jsonb_agg(jsonb_build_object('id', dc.id, 'nom', dc.nom) ORDER BY dc.nom) AS dossiers
           FROM fichiers_dossiers_catalogue_public fd
             JOIN dossiers_catalogue_public dc ON dc.id = fd.dossier_id
          GROUP BY fd.fichier_id) d ON d.fichier_id = b.id;
