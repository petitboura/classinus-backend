/*
04/11/2026, demande Bourama : Muse Glimmer 30B chez Meta, servi par Vultr Serverless Inference, et
reequilibrage des paliers Meta. Ordre IMPERATIF (cle unique sur (distributeur, palier)) :
  1. Muse Spark Open quitte essentiel pour intermediaire (niveau 2), sinon collision a l'etape 2.
  2. Muse Glimmer 30B prend essentiel (niveau 1).
  3. Muse Spark 1.3 passe de l'identifiant "-contributor" a l'identifiant standard : les echanges
     des eleves ne doivent jamais entrainer les modeles Meta (corrige un SKU actif en prod).
  4. Muse Wonder (pro, niveau 4) ne change pas.

Colonne vultr_seul (nouvelle) : meme principe que baseten_seul. Un modele "Vultr seul" ne passe QUE
par Vultr (cle VULTR_INFERENCE_API_KEY), il est ouvert a tout le monde meme quand son fournisseur est
en Bientot, et il n'a pas de route de repli. Muse Glimmer n'est pas servi par l'API de Meta.

L'identifiant chez Vultr (modele_id_vultr) est resolu a l'appel contre le vrai catalogue Vultr
(GET /v1/models) : un suffixe de date ajoute par Vultr est pris en compte automatiquement.

Rejouable sans risque : chaque etape est conditionnee a l'etat de depart.
*/

ALTER TABLE public.modeles_llm ADD COLUMN IF NOT EXISTS vultr_seul boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN public.modeles_llm.vultr_seul IS 'true = modele servi uniquement par Vultr Serverless Inference (cle VULTR_INFERENCE_API_KEY, identifiant dans modele_id_vultr) : ouvert a tout le monde malgre le Bientot de son fournisseur, sans route de repli. Lu par le backend (cache environ 1 minute).';

-- 1. Muse Spark Open : essentiel -> intermediaire (niveau 2)
UPDATE public.modeles_llm
SET palier = 'intermediaire', niveau = 2, updated_at = now()
WHERE distributeur = 'meta' AND palier = 'essentiel' AND modele_id = 'muse-spark-open';

-- 2. Muse Glimmer 30B : essentiel (niveau 1), Vultr seul
INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label, actif, modele_id_vultr, vultr_seul)
VALUES ('meta', 'essentiel', 1, 'muse-glimmer-30b', 'Muse Glimmer 30B', true, 'muse-glimmer-30b', true)
ON CONFLICT (distributeur, palier) DO UPDATE
SET niveau = EXCLUDED.niveau, modele_id = EXCLUDED.modele_id, label = EXCLUDED.label, actif = true,
    modele_id_vultr = EXCLUDED.modele_id_vultr, vultr_seul = true, updated_at = now();

-- 3. Muse Spark 1.3 : identifiant standard, jamais "-contributor"
UPDATE public.modeles_llm
SET modele_id = 'muse-spark-1.3', updated_at = now()
WHERE distributeur = 'meta' AND palier = 'avance' AND modele_id = 'muse-spark-1.3-contributor';
