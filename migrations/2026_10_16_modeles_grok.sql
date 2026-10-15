-- 16/10/2026, demande de Bourama : ajout de Grok (xAI) dans le sélecteur de
-- modèles, avec seulement deux modèles : grok-4.3 (niveaux essentiel et
-- avance) et grok-4.7 (niveau pro). Ni grok-build-0.1 (modèle de code), ni
-- grok-4.20-multi-agent (recherche approfondie en bêta).
--
-- Place dans la hiérarchie : entre Gemini (3) et DeepSeek (devient 5). Un
-- agent débloqué à Claude, GPT, Gemini ou Grok voit donc Grok ; un agent
-- débloqué à DeepSeek ne le voit pas.
--
-- Statut Bientôt : Grok s'affiche grisé tant que bientot vaut true. Pour le
-- rendre utilisable : ajouter la clé XAI_API_KEY sur Railway, puis
--   UPDATE public.fournisseurs_llm SET bientot = false WHERE distributeur = 'grok';
-- (le backend relit la configuration environ chaque minute).
--
-- Le script peut être rejoué sans risque : rien ne change si Grok existe déjà.

-- 1. Libérer la place 4 : DeepSeek passe en 5 (une seule ligne concernée, la
-- contrainte d'unicité de ordre n'est donc jamais violée).
UPDATE public.fournisseurs_llm
SET ordre = 5, updated_at = now()
WHERE distributeur = 'deepseek'
  AND ordre = 4
  AND NOT EXISTS (SELECT 1 FROM public.fournisseurs_llm WHERE distributeur = 'grok');

-- 2. Le fournisseur Grok, en Bientôt.
INSERT INTO public.fournisseurs_llm (distributeur, ordre, bientot, cle_api_requise, variable_cle_api) VALUES
    ('grok', 4, true, true, 'XAI_API_KEY')
ON CONFLICT (distributeur) DO NOTHING;

-- 3. Ses deux modèles sur trois niveaux.
INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label) VALUES
    ('grok', 'essentiel', 1, 'grok-4.3', 'Grok 4.3'),
    ('grok', 'avance', 2, 'grok-4.3', 'Grok 4.3'),
    ('grok', 'pro', 3, 'grok-4.7', 'Grok 4.7')
ON CONFLICT (distributeur, palier) DO NOTHING;
