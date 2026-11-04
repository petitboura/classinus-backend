-- 04/11/2026, hackathon Vultr Agent Rush : ajout de Vultr Serverless Inference comme
-- fournisseur du sélecteur de modèles (branche feat/vultr-agent-rush).
--
-- CE SCRIPT NE S'APPLIQUE PAS TOUT SEUL : à lancer à la main dans le bon projet Supabase
-- (staging d'abord), après avoir testé les modèles avec de vrais appels.
--
-- Étapes, dans cet ordre :
--   1. Poser la clé Serverless Inference de Vultr dans la variable VULTR_INFERENCE_API_KEY
--      du serveur (Render staging ou Railway). Sans elle, Vultr reste invisible.
--   2. Lancer `python scripts/sonder_vultr.py` : il liste les modèles que Vultr propose. Puis
--      `python scripts/sonder_vultr.py --modeles ID1 ID2 --efforts --voir-code` pour tester
--      appels d'outils, vision et code. Aucun identifiant n'est deviné ici : on ne garde que
--      ceux qui répondent OK.
--   3. Lancer la PREMIÈRE partie de ce script (le fournisseur). Sans modèle, rien n'apparaît
--      encore dans le sélecteur.
--   4. Décommenter et remplir la DEUXIÈME partie avec les identifiants testés, puis la lancer.
--   5. Pour rendre Vultr utilisable : UPDATE public.fournisseurs_llm SET bientot = false
--      WHERE distributeur = 'vultr';  (le backend relit la configuration environ chaque minute).
--
-- Place dans la hiérarchie : en dernier, après Meta (ordre 7). Un agent débloqué à Claude,
-- GPT, Gemini, DeepSeek, Grok ou Meta verra donc Vultr quand il sera utilisable.
--
-- Nom affiché (nom_affiche) : Vultr héberge des modèles d'autres créateurs. Le nom affiché dans
-- l'identité du modèle (« propulsé par ... ») devrait être celui du créateur du modèle choisi,
-- à régler avec : UPDATE public.fournisseurs_llm SET nom_affiche = '...' WHERE distributeur = 'vultr';
--
-- Aucune donnée liée à un compte utilisateur n'est créée ici : rien à ajouter à la purge de compte
-- ni à l'export.
--
-- Le script peut être rejoué sans risque : rien ne change si Vultr existe déjà.

-- PREMIÈRE PARTIE : le fournisseur.
INSERT INTO public.fournisseurs_llm (distributeur, ordre, bientot, cle_api_requise, variable_cle_api, nom_affiche) VALUES
    ('vultr', 7, true, true, 'VULTR_INFERENCE_API_KEY', 'Vultr')
ON CONFLICT (distributeur) DO NOTHING;

-- DEUXIÈME PARTIE : les modèles, à remplir avec les identifiants testés par scripts/sonder_vultr.py.
-- Niveaux : la numérotation n'est pas la même partout (voir la migration Meta du 28/10/2026), le
-- script reprend donc le niveau déjà utilisé par le même palier dans la base où il est lancé.
-- Un fournisseur peut avoir un seul modèle (comme DeepSeek, qui en partage un entre deux paliers).
--
-- INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label)
-- SELECT 'vultr', 'avance',
--        COALESCE((SELECT min(niveau) FROM public.modeles_llm WHERE palier = 'avance'), 2),
--        '<IDENTIFIANT EXACT TESTÉ>', '<NOM AFFICHÉ>'
-- ON CONFLICT (distributeur, palier) DO NOTHING;
