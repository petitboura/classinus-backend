/*
Domaines autorisés par l'élève pour une conversation (outil d'exécution de code).
Quand le modèle a besoin d'un domaine absent de execution_code_configuration.allowed_domains,
l'élève confirme (outil sensible gerer_execution_code:demander_acces_reseau) et le domaine est
enregistré ici pour cette conversation seulement. Les lignes d'une conversation sont supprimées à
la fermeture de son workspace, et celles d'un compte à la suppression du compte (ON DELETE CASCADE,
et core/purge_compte.py).
Réexécutable. Seul le service-role du backend utilise cette table, pas de policy côté client.
*/
CREATE TABLE IF NOT EXISTS public.execution_code_domaines_conversation (
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id text NOT NULL CHECK (char_length(conversation_id) BETWEEN 1 AND 200),
    domain text NOT NULL CHECK (char_length(domain) BETWEEN 3 AND 253),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, conversation_id, domain)
);
ALTER TABLE public.execution_code_domaines_conversation ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.execution_code_domaines_conversation FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.execution_code_domaines_conversation TO service_role;

-- Nombre maximal de domaines que l'élève peut ouvrir par conversation (0 désactive la fonction).
ALTER TABLE public.execution_code_configuration
    ADD COLUMN IF NOT EXISTS max_user_domains integer NOT NULL DEFAULT 10
    CHECK (max_user_domains BETWEEN 0 AND 50);
