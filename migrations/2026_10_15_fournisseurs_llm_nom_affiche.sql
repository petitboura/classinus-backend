/*
  15/10/2026, demande Bourama : l'assistant se présente comme l'assistant de
  Classinus, propulsé par le fournisseur puis le modèle (voir
  core/identite_modele.py). Le nom du fournisseur tel qu'il est dit au modèle
  se règle ici, sans toucher au code.

  Appliquée le 15/10/2026 sur Clovis-staging et sur la production (Classinus).

  Colonne facultative : si elle est vide, le backend utilise le nom de repli
  écrit dans le code. Le script peut être rejoué sans risque (IF NOT EXISTS, et
  seules les lignes encore vides sont remplies).
*/

ALTER TABLE public.fournisseurs_llm
    ADD COLUMN IF NOT EXISTS nom_affiche text;

COMMENT ON COLUMN public.fournisseurs_llm.nom_affiche IS 'Nom du fournisseur tel que l''assistant le dit quand on lui demande qui il est (par exemple Anthropic, OpenAI, Google, DeepSeek). Vide = nom de repli du code.';

UPDATE public.fournisseurs_llm AS f
SET nom_affiche = v.nom_affiche
FROM (VALUES
    ('claude', 'Anthropic'),
    ('gpt', 'OpenAI'),
    ('gemini', 'Google'),
    ('deepseek', 'DeepSeek')
) AS v(distributeur, nom_affiche)
WHERE f.distributeur = v.distributeur
  AND f.nom_affiche IS NULL;
