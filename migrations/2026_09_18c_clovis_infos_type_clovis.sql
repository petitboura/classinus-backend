-- Chantier "profil contributeur bibliotheque publique", étape 13
-- (demande Bourama, 18/09/2026) : Clovis lui-même comme 4e type
-- d'élément cible pour les commentaires et les étoiles.
--
-- Système générique (type_element, element_id), sur les tables DE CE
-- CHANTIER uniquement -- explicitement PAS agent_comments/agent_ratings
-- (ancien système historique, voir core/serveur_mcp_espace.py) : il n'y
-- a plus de système "agent" dans Clovis, ce nommage est volontairement
-- banni ici.
--
-- clovis_infos : table singleton (une seule ligne, id fixe) qui joue le
-- même rôle que bibliotheque_publique/dossiers_catalogue_public/
-- comportements_publics pour les 3 autres types -- juste une cible pour
-- etoiles_count et pour la contrainte d'existence de element_id (les
-- commentaires n'ont pas besoin de compteur dénormalisé, voir
-- core/commentaires_catalogue_public.py::lister_commentaires qui compte
-- directement).
--
-- Note : cette migration documente a posteriori un état déjà appliqué
-- en base (via l'outil MCP Supabase), pas un changement de schéma à
-- exécuter à nouveau.

CREATE TABLE IF NOT EXISTS public.clovis_infos (
    id uuid PRIMARY KEY,
    etoiles_count integer NOT NULL DEFAULT 0
);

INSERT INTO public.clovis_infos (id)
VALUES ('00000000-0000-0000-0000-000000000001')
ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.clovis_infos ENABLE ROW LEVEL SECURITY;
-- Aucune policy : accès exclusivement via la clé service_role (backend),
-- même logique que les tables voisines du projet.

ALTER TABLE public.commentaires_catalogue_public
    DROP CONSTRAINT commentaires_catalogue_public_type_element_check,
    ADD CONSTRAINT commentaires_catalogue_public_type_element_check
        CHECK (type_element = ANY (ARRAY['fichier'::text, 'dossier'::text, 'skill'::text, 'clovis'::text]));

ALTER TABLE public.etoiles_catalogue_public
    DROP CONSTRAINT etoiles_catalogue_public_type_element_check,
    ADD CONSTRAINT etoiles_catalogue_public_type_element_check
        CHECK (type_element = ANY (ARRAY['fichier'::text, 'dossier'::text, 'skill'::text, 'clovis'::text]));
