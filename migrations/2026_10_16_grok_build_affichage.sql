-- 16/10/2026, demande de Bourama : afficher grok-build-0.1 (modèle de code de
-- xAI) dans le sélecteur, grisé avec la mention Bientôt, sans le brancher
-- nulle part. Grok est déjà en Bientôt (voir 2026_10_16_modeles_grok.sql).
--
-- Un fournisseur n'a qu'une ligne par niveau (essentiel, avance, pro), et
-- Grok les utilise déjà : grok-build-0.1 prend donc un quatrième niveau,
-- "specialise", que aucun agent n'a débloqué. Il n'est jamais choisissable
-- et ne sert qu'à l'affichage Bientôt. Rejouable sans risque.

INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label) VALUES
    ('grok', 'specialise', 4, 'grok-build-0.1', 'Grok Build 0.1')
ON CONFLICT (distributeur, palier) DO NOTHING;
