-- Chantier profil contributeur / analytique bibliothèque publique (demande
-- Bourama, 18/09/2026, étape 2).
--
-- Commentaires sur un élément du catalogue public (fichier, dossier ou
-- skill) -- système générique par (type_element, element_id), indépendant
-- du système d'étoiles (voir migration etoiles_catalogue_public, qui n'est
-- pas un système de note chiffrée mais un simple compteur "une étoile par
-- personne", façon GitHub).
--
-- Distinct et sans lien avec agent_comments/agent_ratings (avis sur
-- Clovis lui-même) : deux systèmes séparés, non touchés par ce chantier.
--
-- Note : cette migration documente a posteriori un état déjà appliqué en
-- base (table créée via l'outil Supabase avant d'être versionnée ici),
-- pas un changement de schéma à exécuter à nouveau.

CREATE TABLE IF NOT EXISTS public.commentaires_catalogue_public (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type_element text NOT NULL CHECK (type_element IN ('fichier', 'dossier', 'skill')),
    element_id uuid NOT NULL,
    utilisateur_id uuid NOT NULL REFERENCES auth.users(id),
    contenu text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_commentaires_catalogue_public_element
    ON public.commentaires_catalogue_public USING btree (type_element, element_id);

ALTER TABLE public.commentaires_catalogue_public ENABLE ROW LEVEL SECURITY;
-- Aucune policy définie : accès exclusivement via la clé service_role
-- (backend), même logique que les tables voisines du projet.
