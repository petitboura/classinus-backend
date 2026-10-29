-- 29/10/2026, demande Bourama : routage DeepSeek par Baseten (staging d'abord).
-- C'est le MEME DeepSeek dans le selecteur : seule la route change derriere.
-- Interrupteur : colonne baseten_actif (OFF par defaut = direct comme avant,
-- Bourama seul decide quand l'allumer). Slugs : colonne modele_id_baseten
-- (identifiants chez Baseten, doc officielle page Reasoning, 29/10/2026).
-- Le backend relit cette configuration environ chaque minute ; sans ces
-- colonnes (migration pas encore appliquee), il se comporte comme avant.
--
-- Slugs verifies le 29/10/2026 (docs.baseten.co, page Reasoning) :
--   pro (deepseek-v4-pro) -> deepseek-ai/DeepSeek-V4-Pro-0813
--   flash (deepseek-v4-flash) -> deepseek-ai/DeepSeek-V4-Flash-0731
--
-- Le script peut etre rejoue sans risque (IF NOT EXISTS, UPDATE conditionnes).
--
-- Pour activer Baseten (quand la cle BASETEN_API_KEY est posee sur le serveur) :
--   UPDATE public.fournisseurs_llm SET baseten_actif = true WHERE distributeur = 'deepseek';
-- Pour revenir au direct :
--   UPDATE public.fournisseurs_llm SET baseten_actif = false WHERE distributeur = 'deepseek';

ALTER TABLE public.fournisseurs_llm ADD COLUMN IF NOT EXISTS baseten_actif boolean NOT NULL DEFAULT false;
ALTER TABLE public.modeles_llm ADD COLUMN IF NOT EXISTS modele_id_baseten text;

COMMENT ON COLUMN public.fournisseurs_llm.baseten_actif IS 'true = les appels de ce fournisseur passent par Baseten (cle BASETEN_API_KEY), avec repli auto vers le direct si Baseten refuse (credit epuise). Aujourd''hui seul deepseek l''utilise. Lu par le backend (cache environ 1 minute).';
COMMENT ON COLUMN public.modeles_llm.modele_id_baseten IS 'Identifiant du modele chez Baseten (slug), envoye a la place de modele_id quand baseten_actif vaut true. NULL = jamais servi par Baseten.';

UPDATE public.modeles_llm SET modele_id_baseten = 'deepseek-ai/DeepSeek-V4-Flash-0731'
WHERE distributeur = 'deepseek' AND modele_id = 'deepseek-v4-flash' AND modele_id_baseten IS NULL;

UPDATE public.modeles_llm SET modele_id_baseten = 'deepseek-ai/DeepSeek-V4-Pro-0813'
WHERE distributeur = 'deepseek' AND modele_id = 'deepseek-v4-pro' AND modele_id_baseten IS NULL;
