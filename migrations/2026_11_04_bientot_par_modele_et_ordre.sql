/*
04/11/2026, demande Bourama :
1. DeepSeek Pro et Muse Spark Open passent en Bientot, modele par modele (nouvelle colonne
   modeles_llm.bientot). Le fournisseur reste ouvert, seul le modele est ferme.
2. Exception : les adresses de la table acces_anticipe_modeles (ceux qui voient tout) gardent ces
   modeles. Elles etaient deja listees pour Claude, GPT, Gemini, Grok et Meta : on les ajoute aussi
   pour DeepSeek, sinon DeepSeek Pro leur serait ferme.
3. Fournisseurs reordonnes : en haut ceux qui ont le plus de modeles pas en Bientot (Z.ai 2, Alibaba 2,
   DeepSeek 1, Meta 1, NVIDIA 1, puis Claude, GPT, Gemini, Grok qui sont entierement en Bientot).
   La colonne ordre est aussi la hierarchie de deblocage des agents (le premier debloque tout ce qui le
   suit) : l'agent qui avait "meta" passe a "zai" pour garder exactement les memes fournisseurs.

Rejouable sans risque.
*/

ALTER TABLE public.modeles_llm ADD COLUMN IF NOT EXISTS bientot boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN public.modeles_llm.bientot IS 'true = modele affiche Bientot meme si son fournisseur est ouvert ; reste utilisable par les adresses de acces_anticipe_modeles pour ce fournisseur. Lu par le backend (cache environ 1 minute).';

UPDATE public.modeles_llm
SET bientot = true, updated_at = now()
WHERE (distributeur = 'deepseek' AND palier = 'pro')
   OR (distributeur = 'meta' AND palier = 'intermediaire' AND modele_id = 'muse-spark-open');

INSERT INTO public.acces_anticipe_modeles (distributeur, email)
SELECT DISTINCT 'deepseek', email FROM public.acces_anticipe_modeles
ON CONFLICT (distributeur, email) DO NOTHING;

UPDATE public.fournisseurs_llm SET ordre = ordre + 100;
UPDATE public.fournisseurs_llm
SET ordre = CASE distributeur
      WHEN 'zai' THEN 1 WHEN 'alibaba' THEN 2 WHEN 'deepseek' THEN 3 WHEN 'meta' THEN 4
      WHEN 'nvidia' THEN 5 WHEN 'claude' THEN 6 WHEN 'gpt' THEN 7 WHEN 'gemini' THEN 8 WHEN 'grok' THEN 9
      ELSE ordre END,
    updated_at = now();

UPDATE public.agents SET distributeur_debloque = 'zai' WHERE distributeur_debloque = 'meta';
