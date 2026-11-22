-- 18/11/2026, demande de Bourama : les paliers techniques sont alignes sur leur niveau numerique,
-- le numero fait foi. 1 = essentiel, 2 = pro, 3 = premium, 4 = max, 5 = ultra, 6 = specialise.
--   intermediaire (2) -> pro
--   avance (3)        -> premium
--   pro (4)           -> max
--   premium (5)       -> ultra
-- Concerne modeles_llm.palier et agents.palier_debloque (un agent garde son niveau numerique).
-- Passe par des noms temporaires pour ne jamais heurter une contrainte d'unicite en cours de route.
-- Ne s'execute qu'une fois : le bloc est ignore des que "avance" et "intermediaire" n'existent plus.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM modeles_llm WHERE palier IN ('avance', 'intermediaire')) THEN
    UPDATE modeles_llm SET palier = CASE palier
      WHEN 'intermediaire' THEN 'tmp_pro'
      WHEN 'avance' THEN 'tmp_premium'
      WHEN 'pro' THEN 'tmp_max'
      WHEN 'premium' THEN 'tmp_ultra'
    END
    WHERE palier IN ('intermediaire', 'avance', 'pro', 'premium');
    UPDATE modeles_llm SET palier = substr(palier, 5) WHERE palier LIKE 'tmp\_%';

    UPDATE agents SET palier_debloque = CASE palier_debloque
      WHEN 'intermediaire' THEN 'pro'
      WHEN 'avance' THEN 'premium'
      WHEN 'pro' THEN 'max'
      WHEN 'premium' THEN 'ultra'
    END
    WHERE palier_debloque IN ('intermediaire', 'avance', 'pro', 'premium');
  END IF;
END $$;
