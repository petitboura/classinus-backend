-- 15/10/2026, demande Bourama : tout ce qui concerne les modèles du sélecteur
-- (statut Bientôt, mot Bientôt, liste des modèles, règle de clé API) se règle
-- dans Supabase, sans toucher au code (voir core/fournisseurs_llm.py). Le
-- backend relit ces trois tables environ chaque minute et garde les valeurs du
-- code comme repli si la lecture échoue ou si les tables sont vides.
--
-- Appliquée sur Clovis-staging le 15/10/2026. Pas encore appliquée en
-- production : tant que ces tables n'y existent pas, le backend utilise les
-- valeurs de repli du code, donc rien ne casse. Le script peut être rejoué sans
-- risque (IF NOT EXISTS et ON CONFLICT DO NOTHING).
--
-- Les tables sont lues avec la clé de service du backend. RLS est activée sans
-- aucune politique : aucun accès direct depuis un navigateur.

CREATE TABLE IF NOT EXISTS public.fournisseurs_llm (
    distributeur text PRIMARY KEY,
    ordre integer NOT NULL UNIQUE,
    bientot boolean NOT NULL DEFAULT false,
    cle_api_requise boolean NOT NULL DEFAULT true,
    variable_cle_api text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.modeles_llm (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    distributeur text NOT NULL REFERENCES public.fournisseurs_llm(distributeur) ON UPDATE CASCADE ON DELETE CASCADE,
    palier text NOT NULL,
    niveau integer NOT NULL,
    modele_id text NOT NULL,
    label text NOT NULL,
    actif boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (distributeur, palier)
);

CREATE TABLE IF NOT EXISTS public.textes_modeles_llm (
    cle text NOT NULL,
    langue text NOT NULL,
    texte text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (cle, langue)
);

ALTER TABLE public.fournisseurs_llm ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.modeles_llm ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.textes_modeles_llm ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.fournisseurs_llm IS 'Fournisseurs de modèles (Claude, GPT, Gemini, DeepSeek) : ordre de la hiérarchie, statut Bientôt, règle de clé API. Lu par le backend (cache environ 1 minute).';
COMMENT ON COLUMN public.fournisseurs_llm.ordre IS 'Hiérarchie cumulative : 1 est le plus haut. Débloquer un fournisseur donne accès à tous ceux qui ont un ordre plus grand.';
COMMENT ON COLUMN public.fournisseurs_llm.bientot IS 'true = modèles du fournisseur affichés grisés avec la mention Bientôt, jamais choisissables (prime sur la clé API et le déblocage).';
COMMENT ON COLUMN public.fournisseurs_llm.cle_api_requise IS 'true = le fournisseur disparaît si sa clé API est absente du serveur. false = visible sans vérifier la clé.';
COMMENT ON COLUMN public.fournisseurs_llm.variable_cle_api IS 'Nom de la variable d''environnement du serveur qui contient la clé API (par exemple DEEPSEEK_API_KEY).';
COMMENT ON TABLE public.modeles_llm IS 'Un modèle par ligne : fournisseur, niveau (palier), identifiant chez le fournisseur et nom affiché.';
COMMENT ON COLUMN public.modeles_llm.palier IS 'Nom du niveau, doit correspondre à palier_debloque des agents (essentiel, avance, pro).';
COMMENT ON COLUMN public.modeles_llm.niveau IS 'Rang du palier : 1 le plus bas. Un agent débloqué à un niveau voit aussi les niveaux plus bas.';
COMMENT ON COLUMN public.modeles_llm.modele_id IS 'Identifiant exact du modèle chez le fournisseur.';
COMMENT ON COLUMN public.modeles_llm.actif IS 'false = modèle retiré de toutes les listes.';
COMMENT ON TABLE public.textes_modeles_llm IS 'Textes affichés dans le sélecteur de modèle, par langue (cle = bientot, par exemple).';

INSERT INTO public.fournisseurs_llm (distributeur, ordre, bientot, cle_api_requise, variable_cle_api) VALUES
    ('claude', 1, true, true, 'ANTHROPIC_API_KEY'),
    ('gpt', 2, true, true, 'OPENAI_API_KEY'),
    ('gemini', 3, true, true, 'GOOGLE_API_KEY'),
    ('deepseek', 4, false, true, 'DEEPSEEK_API_KEY')
ON CONFLICT (distributeur) DO NOTHING;

INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label) VALUES
    ('claude', 'essentiel', 1, 'claude-haiku-4-5-20251001', 'Claude Haiku 4.5'),
    ('claude', 'avance', 2, 'claude-sonnet-5', 'Claude Sonnet 5'),
    ('claude', 'pro', 3, 'claude-opus-4-8', 'Claude Opus 4.8'),
    ('gpt', 'essentiel', 1, 'gpt-5-nano', 'GPT-5 nano'),
    ('gpt', 'avance', 2, 'gpt-5.4', 'GPT-5.4'),
    ('gpt', 'pro', 3, 'gpt-5.5', 'GPT-5.5'),
    ('gemini', 'essentiel', 1, 'gemini-3.5-flash-lite', 'Gemini 3.5 Flash-Lite'),
    ('gemini', 'avance', 2, 'gemini-3.6-flash', 'Gemini 3.6 Flash'),
    ('gemini', 'pro', 3, 'gemini-3.1-pro', 'Gemini 3.1 Pro'),
    ('deepseek', 'essentiel', 1, 'deepseek-v4-flash', 'DeepSeek V4 Flash'),
    ('deepseek', 'avance', 2, 'deepseek-v4-flash', 'DeepSeek V4 Flash'),
    ('deepseek', 'pro', 3, 'deepseek-v4-pro', 'DeepSeek V4 Pro')
ON CONFLICT (distributeur, palier) DO NOTHING;

INSERT INTO public.textes_modeles_llm (cle, langue, texte) VALUES ('bientot', 'fr', 'Bientôt')
ON CONFLICT (cle, langue) DO NOTHING;
