-- Item 2 des specs indépendantes ScholarFlow AI (volet étudiant),
-- 14/09/2026, demande Bourama : historique des réponses données par un
-- étudiant à un QCM généré (format ```qcm, voir item 5 dans
-- core/profils_agents.py). En vue d'un futur écran de suivi (pas
-- construit maintenant) -- pour l'instant affiché seulement dans le fil
-- de conversation et l'historique, aucun écran de consultation dédié.
--
-- ATTENTION NOM (répété volontairement, point d'audit critique du même
-- type que conversation_persona_pedagogique) : ne jamais utiliser "mode"
-- dans le nom de cette table ou de ses colonnes -- ce mot est déjà pris
-- par conversation_mode_actif (rattachement enseignant/code de classe),
-- un concept totalement différent.
--
-- Schéma aligné sur le format JSON du bloc ```qcm (item 5) et de
-- QCMInteractif.tsx (item 3) : {question, choix[], reponse (index),
-- explication?}. reponse_choisie/reponse_correcte stockent l'index
-- (0-based) dans choix, pas le texte, pour rester compact et cohérent
-- avec le format déjà utilisé côté affichage.

CREATE TABLE IF NOT EXISTS public.historique_reponses_qcm (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL,
    user_id uuid NOT NULL,
    question text NOT NULL,
    choix jsonb NOT NULL,
    reponse_choisie integer NOT NULL,
    reponse_correcte integer NOT NULL,
    explication text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_historique_reponses_qcm_conversation
    ON public.historique_reponses_qcm USING btree (conversation_id);

CREATE INDEX IF NOT EXISTS idx_historique_reponses_qcm_user
    ON public.historique_reponses_qcm USING btree (user_id);

ALTER TABLE public.historique_reponses_qcm ENABLE ROW LEVEL SECURITY;
-- Aucune policy définie : accès exclusivement via la clé service_role
-- (backend), même logique que conversation_persona_pedagogique et le
-- reste des tables internes du projet.
