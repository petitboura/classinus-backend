-- 16/10/2026, demande de Bourama : ajout de Grok (xAI) dans le sélecteur de
-- modèles, avec deux modèles : grok-4.3 (niveaux essentiel et avance) et
-- grok-4.7 (niveau pro). Le modèle de code grok-build-0.1 est ajouté à part
-- (voir 2026_10_16_grok_build_affichage.sql) ; grok-4.20-multi-agent n'est
-- pas ajouté.
--
-- Place dans la hiérarchie : en dernier, après DeepSeek (ordre 5). Un agent
-- débloqué à Claude, GPT, Gemini ou DeepSeek voit donc Grok quand il est
-- utilisable.
--
-- Statut Bientôt : Grok s'affiche grisé tant que bientot vaut true. Pour le
-- rendre utilisable : ajouter la clé XAI_API_KEY sur Railway, puis
--   UPDATE public.fournisseurs_llm SET bientot = false WHERE distributeur = 'grok';
-- (le backend relit la configuration environ chaque minute).
--
-- Le script peut être rejoué sans risque : rien ne change si Grok existe déjà.

INSERT INTO public.fournisseurs_llm (distributeur, ordre, bientot, cle_api_requise, variable_cle_api) VALUES
    ('grok', 5, true, true, 'XAI_API_KEY')
ON CONFLICT (distributeur) DO NOTHING;

INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label) VALUES
    ('grok', 'essentiel', 1, 'grok-4.3', 'Grok 4.3'),
    ('grok', 'avance', 2, 'grok-4.3', 'Grok 4.3'),
    ('grok', 'pro', 3, 'grok-4.7', 'Grok 4.7')
ON CONFLICT (distributeur, palier) DO NOTHING;
