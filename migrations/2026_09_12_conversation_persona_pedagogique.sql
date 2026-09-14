-- Item 9 des specs indépendantes ScholarFlow AI (volet étudiant),
-- 12/09/2026, demande Bourama : mode pédagogique actif par conversation
-- (Socratique / Professeur / Tuteur / Examinateur -- voir
-- MODES_PEDAGOGIQUES dans core/profils_agents.py, item 1).
--
-- ATTENTION NOM (répété volontairement, point d'audit critique) : ne pas
-- confondre avec conversation_mode_actif (migration 2026_09_06), qui
-- désigne le rattachement enseignant/code de classe actif sur une
-- conversation -- un concept totalement différent. D'où le nom distinct
-- conversation_persona_pedagogique ici, et core/persona_pedagogique_conversation.py
-- côté code (jamais core/mode_actif_conversation.py, déjà pris).
--
-- Cette table ne fait que stocker le choix de l'étudiant. Elle n'est pas
-- encore lue au moment de construire le prompt système envoyé au modèle
-- (jonction restante, hors scope de cet item -- voir specs-independantes.md).

CREATE TABLE IF NOT EXISTS public.conversation_persona_pedagogique (
    conversation_id uuid PRIMARY KEY,
    user_id uuid NOT NULL,
    persona text CHECK (persona IN ('socratique', 'professeur', 'tuteur', 'examinateur')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_persona_pedagogique_user
    ON public.conversation_persona_pedagogique USING btree (user_id);

ALTER TABLE public.conversation_persona_pedagogique ENABLE ROW LEVEL SECURITY;
-- Aucune policy définie : accès exclusivement via la clé service_role
-- (backend), même logique que conversation_mode_actif et le reste des
-- tables internes du projet.
