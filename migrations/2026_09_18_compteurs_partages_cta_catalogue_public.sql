-- Chantier profil contributeur / analytique bibliothèque publique (demande
-- Bourama, 18/09/2026, étape 3).
--
-- Compteurs dénormalisés pour l'analytique par élément public (fichier ou
-- dossier) : partages_count (nombre de clics sur le bouton "partager",
-- simple compteur brut -- pas de table de log par utilisateur, à la
-- différence des étoiles) et cta_count (nombre de clics sur BoutonAvecIA,
-- voir étape 6/12 pour l'endpoint d'incrément et l'instrumentation).
-- Même principe que etoiles_count (migration etoiles_catalogue_public) :
-- jamais recompter à l'affichage.
--
-- Note : cette migration documente a posteriori un état déjà appliqué en
-- base (colonnes créées via l'outil Supabase avant d'être versionnées
-- ici), pas un changement de schéma à exécuter à nouveau.

ALTER TABLE public.bibliotheque_publique
    ADD COLUMN IF NOT EXISTS partages_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cta_count integer NOT NULL DEFAULT 0;

ALTER TABLE public.dossiers_catalogue_public
    ADD COLUMN IF NOT EXISTS partages_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cta_count integer NOT NULL DEFAULT 0;
