-- Chantier "mode source" (voir contexte-mode-source-clovis.md), demande
-- Bourama, 16/09/2026.
--
-- Stocke le mode source actif d'une conversation : quelles sources Clovis
-- a le droit d'utiliser pour repondre (Aucun / Recherche / Sur pieces).
-- Meme principe et meme forme que conversation_persona_pedagogique
-- (migration 2026_09_12) et conversation_guide_actif (migration
-- 2026_09_16b) : un choix explicite de l'eleve, jamais une valeur par
-- defaut implicite. "Aucun" correspond a l'absence de ligne (aucune
-- contrainte ne change), pas a une valeur stockee a part.
--
-- ATTENTION NOM (repete volontairement, meme point d'audit critique que
-- les tables voisines) : NE PAS confondre avec conversation_mode_actif
-- (migration 2026_09_06, rattachement enseignant/code de classe) ni avec
-- conversation_persona_pedagogique (style d'enseignement de Clovis).
-- Trois concepts independants qui cohabitent sur la meme conversation.
-- D'ou le nom distinct conversation_mode_source ici, et
-- core/mode_source_conversation.py cote code.
--
-- Visible et modifiable par tout le monde, majeurs et mineurs (a la
-- difference du "Aucun mode" de conversation_mode_actif, reserve aux
-- majeurs) : aucune regle de verrouillage ici.

CREATE TABLE IF NOT EXISTS public.conversation_mode_source (
    conversation_id uuid PRIMARY KEY,
    user_id uuid NOT NULL,
    mode_source text CHECK (mode_source IN ('recherche', 'sur_pieces')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_mode_source_user
    ON public.conversation_mode_source USING btree (user_id);

ALTER TABLE public.conversation_mode_source ENABLE ROW LEVEL SECURITY;
-- Aucune policy definie : acces exclusivement via la cle service_role
-- (backend), meme logique que les tables voisines du projet.
