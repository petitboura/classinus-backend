-- 19/11/2026, demande de Bourama : les paliers suivent les groupes, du moins fort au plus fort.
--   groupe 5 -> essentiel (1)   groupe 4 -> pro (2)   groupe 3 -> premium (3)
--   groupe 2 -> max (4)         groupe 1 -> ultra (5)
-- Exceptions voulues : Muse Spark Open (pas de groupe), DeepSeek V4.1 Flash (groupe 5) et Grok Build 0.1
-- (groupe 4, ex "specialise") sont tous les trois au palier pro (2).
-- Grok 4.3 (ids 13 et 14) et DeepSeek V4.1 Flash (ids 10 et 11) avaient chacun deux lignes identiques,
-- une par palier couvert : une seule ligne par fournisseur et palier est permise, la seconde est retiree.
-- L'agent qui avait "max" passe a "ultra" pour continuer a voir tous les modeles.
-- Ne s'execute qu'une fois : ignore des que la ligne en double (id 11) n'existe plus.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM modeles_llm WHERE id = 11 AND modele_id = 'deepseek-v4-flash') THEN
    DELETE FROM modeles_llm WHERE id = 11 AND modele_id = 'deepseek-v4-flash';
    DELETE FROM modeles_llm WHERE id = 14 AND modele_id = 'grok-4.3';

    UPDATE modeles_llm m
    SET niveau = c.n,
        palier = 'tmp_' || (ARRAY['essentiel', 'pro', 'premium', 'max', 'ultra'])[c.n]
    FROM (
      SELECT id,
        CASE WHEN id IN (10, 16, 21) THEN 2
             ELSE CASE groupe WHEN 1 THEN 5 WHEN 2 THEN 4 WHEN 3 THEN 3 WHEN 4 THEN 2 WHEN 5 THEN 1 END
        END AS n
      FROM modeles_llm
    ) c
    WHERE c.id = m.id AND c.n IS NOT NULL;
    UPDATE modeles_llm SET palier = substr(palier, 5) WHERE palier LIKE 'tmp\_%';

    UPDATE agents SET palier_debloque = 'ultra' WHERE palier_debloque = 'max';
  END IF;
END $$;
