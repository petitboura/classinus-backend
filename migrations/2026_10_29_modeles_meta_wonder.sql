-- 29/10/2026 : correction de l'identifiant Meta Muse Wonder sur staging.
--
-- La migration 2026_10_28_modeles_meta.sql a inséré le niveau pro de Meta avec
-- l'identifiant 'muse-wonder'. La documentation officielle Meta (page Modèles,
-- https://dev.meta.ai/docs/models, vérifiée le 29/10/2026) donne l'identifiant
-- exact 'muse-wonder-1.0' sur l'API Meta. Le code et la migration du 28/10 ont
-- été corrigés, mais si staging a déjà appliqué l'ancienne version, la ligne
-- garde l'ancien identifiant (le ON CONFLICT DO NOTHING ne corrige rien).
--
-- Cette migration corrige la ligne existante. Elle peut être rejouée sans
-- risque : si la ligne a déjà le bon identifiant (ou si Meta n'est pas encore
-- installé), rien ne change.
--
-- Identifiants standards seulement, jamais "-contributor" : les échanges des
-- élèves ne doivent pas entraîner les modèles Meta.

UPDATE public.modeles_llm
SET modele_id = 'muse-wonder-1.0'
WHERE distributeur = 'meta' AND palier = 'pro' AND modele_id = 'muse-wonder';
