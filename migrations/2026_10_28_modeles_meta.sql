-- 28/10/2026, demande de Bourama : ajout de Meta dans le sélecteur de
-- modèles (staging, Bientôt), avec deux modèles : Muse Spark 1.3 (niveau
-- avance) et Muse Wonder (niveau pro, en préversion, plus cher, affiché tout
-- en haut). Pas de niveau essentiel.
--
-- Place dans la hiérarchie : en dernier, après Grok (ordre 6). Un agent
-- débloqué à Claude, GPT, Gemini, DeepSeek ou Grok verra donc Meta quand il
-- sera utilisable.
--
-- Statut Bientôt : Meta s'affiche grisé tant que bientot vaut true. Pour le
-- rendre utilisable : ajouter la clé MODEL_API_KEY sur Railway staging, puis
--   UPDATE public.fournisseurs_llm SET bientot = false WHERE distributeur = 'meta';
-- (le backend relit la configuration environ chaque minute ; identifiants
-- standards seulement, jamais "-contributor" : les données des élèves ne
-- doivent pas entraîner les modèles Meta).
--
-- Le script peut être rejoué sans risque : rien ne change si Meta existe déjà.

INSERT INTO public.fournisseurs_llm (distributeur, ordre, bientot, cle_api_requise, variable_cle_api, nom_affiche) VALUES
    ('meta', 6, true, true, 'MODEL_API_KEY', 'Meta')
ON CONFLICT (distributeur) DO NOTHING;

INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label) VALUES
    ('meta', 'avance', 2, 'muse-spark-1.3', 'Muse Spark 1.3'),
    ('meta', 'pro', 3, 'muse-wonder-1.0', 'Muse Wonder')
ON CONFLICT (distributeur, palier) DO NOTHING;
