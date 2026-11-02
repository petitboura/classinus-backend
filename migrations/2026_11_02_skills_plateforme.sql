/*
Skills officiels de plateforme (décisions de Bourama, 02/11/2026).

Un skill de plateforme est fourni par Classinus, identique pour tous les comptes, en lecture
seule. Il vit dans la même table que les skills personnels, avec portee = 'plateforme' et sans
propriétaire. Toutes les routes d'écriture existantes filtrent déjà sur owner_id : un skill sans
propriétaire reste donc intouchable depuis le chat et depuis l'API.

Les contenus restent dans R2 (même bucket que les skills personnels). Le script
scripts/synchroniser_skills_plateforme.py les envoie depuis le dossier skills_plateforme/ du dépôt.

Cette migration est réexécutable. Appliquer d'abord sur le Supabase de staging.
*/

/* 1. Un skill de plateforme n'a pas de propriétaire. */
ALTER TABLE public.skills ALTER COLUMN owner_id DROP NOT NULL;

/* 2. Portée et identifiant stable (le slug sert à la synchronisation, jamais à l'affichage). */
ALTER TABLE public.skills ADD COLUMN IF NOT EXISTS portee text NOT NULL DEFAULT 'compte';
ALTER TABLE public.skills ADD COLUMN IF NOT EXISTS slug text;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'skills_portee_check') THEN
        ALTER TABLE public.skills ADD CONSTRAINT skills_portee_check CHECK (portee IN ('compte', 'plateforme'));
    END IF;
    /* Cohérence : plateforme = sans propriétaire et avec slug ; compte = avec propriétaire. */
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'skills_portee_proprietaire_check') THEN
        ALTER TABLE public.skills ADD CONSTRAINT skills_portee_proprietaire_check CHECK (
            (portee = 'plateforme' AND owner_id IS NULL AND slug IS NOT NULL)
            OR (portee = 'compte' AND owner_id IS NOT NULL)
        );
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS skills_plateforme_slug_idx ON public.skills(slug) WHERE portee = 'plateforme';
CREATE INDEX IF NOT EXISTS skills_portee_idx ON public.skills(portee) WHERE portee = 'plateforme';

/*
3. Préférence de l'utilisateur : ne plus lui signaler qu'un skill officiel existe à côté du sien.
Une ligne par utilisateur, créée seulement quand il en exprime le souhait. Supprimée avec le compte.
Seul le service-role du backend y accède, pas de policy côté client.
*/
CREATE TABLE IF NOT EXISTS public.preferences_skills_officiels (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    ne_plus_proposer boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.preferences_skills_officiels ENABLE ROW LEVEL SECURITY;
