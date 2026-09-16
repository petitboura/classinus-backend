-- Etape 2 du chantier "guide de decouverte" (voir specs-guide-decouverte.md
-- dans clovis-frontend), demande Bourama, 16/09/2026.
--
-- Stocke si le guide interactif est actif sur une conversation donnee.
-- Meme principe et meme forme que conversation_persona_pedagogique
-- (migration 2026_09_12) : un choix explicite de l'utilisateur, jamais
-- une valeur par defaut implicite, pas encore lu au moment de construire
-- le prompt systeme (jonction laissee a l'etape 3, hors scope ici -- voir
-- specs-guide-decouverte.md).
--
-- ATTENTION NOM (repete volontairement, meme point d'audit critique que
-- conversation_persona_pedagogique) : NE PAS confondre avec
-- conversation_mode_actif (migration 2026_09_06, rattachement
-- enseignant/code de classe) ni avec guide_sections (migration
-- 2026_09_16, referentiel de contenu statique, etape 1 du meme chantier).
-- D'ou le nom distinct conversation_guide_actif ici, et
-- core/guide_conversation.py cote code (jamais core/mode_guide.py ni
-- core/mode_actif_conversation.py, deja pris).

CREATE TABLE IF NOT EXISTS public.conversation_guide_actif (
    conversation_id uuid PRIMARY KEY,
    user_id uuid NOT NULL,
    actif boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_guide_actif_user
    ON public.conversation_guide_actif USING btree (user_id);

ALTER TABLE public.conversation_guide_actif ENABLE ROW LEVEL SECURITY;
-- Aucune policy definie : acces exclusivement via la cle service_role
-- (backend), meme logique que conversation_persona_pedagogique et le
-- reste des tables internes du projet.
