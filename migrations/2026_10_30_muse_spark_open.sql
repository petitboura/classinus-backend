-- 30/10/2026, demande de Bourama : ajout de Muse Spark Open (Meta, poids ouverts) dans le
-- sélecteur de modèles, juste après Muse Spark 1.3.
--
-- Meta ne sert pas ce modèle par son API : il passe UNIQUEMENT par Baseten
-- (https://inference.baseten.co/v1, clé BASETEN_API_KEY sur le serveur). Il est ouvert à
-- tout le monde : le statut Bientôt de Meta ne s'y applique pas, et il n'apparaît que si la
-- clé Baseten existe. Pas de repli direct : un refus de Baseten remonte comme erreur.
--
-- Colonne baseten_seul (modeles_llm) : true = modèle servi seulement par Baseten. Le slug
-- Baseten est lu dans modele_id_baseten (même colonne que DeepSeek).
--
-- Place : niveau essentiel de Meta (Spark 1.3 = avancé, Wonder = pro). L'ordre du sélecteur
-- va du plus puissant au moins puissant, donc : Muse Wonder, Muse Spark 1.3, Muse Spark Open.
-- Le niveau reprend celui déjà utilisé par le palier essentiel dans la base où le script est
-- lancé (la numérotation diffère entre staging et production).
--
-- Slug Baseten indiqué par Bourama : meta-models/muse-spark-open-1026.
--
-- Le script peut être rejoué sans risque.

ALTER TABLE public.modeles_llm ADD COLUMN IF NOT EXISTS baseten_seul boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.modeles_llm.baseten_seul IS 'true = modèle servi seulement par Baseten (slug dans modele_id_baseten, clé BASETEN_API_KEY) : ouvert à tout le monde malgré le Bientôt du fournisseur, sans repli direct, absent si la clé Baseten manque.';

INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label, modele_id_baseten, baseten_seul)
SELECT 'meta', 'essentiel',
       COALESCE((SELECT min(niveau) FROM public.modeles_llm WHERE palier = 'essentiel'), 1),
       'muse-spark-open', 'Muse Spark Open', 'meta-models/muse-spark-open-1026', true
ON CONFLICT (distributeur, palier) DO NOTHING;
