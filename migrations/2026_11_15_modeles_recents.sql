/*
15/11/2026, demande de Bourama : brancher les modeles les plus recents dans le selecteur.

Ce qui change :
1. Claude, niveau premium : Claude Fable 5.1 devient Claude Fable 5.2 (claude-fable-5-2).
2. GPT, niveau intermediaire : GPT-5.6 Terra devient GPT-6.1 Terra (gpt-6.1-terra).
3. Gemini, niveau avance : Gemini 3.8 Flash devient Gemini 4 Hydrogen (gemini-4-hydrogen).
4. Gemini, nouveau niveau premium : Gemini 4 Carbon (gemini-4-carbon), niveau 5 comme Claude Fable.
5. DeepSeek : l'etiquette V4 Flash devient V4.1 Flash. L'identifiant deepseek-v4-flash ne change
   pas (il sert de cle : modele prefere des eleves, cascade), seul le nom affiche change. Vultr
   sert deja deepseek-v4.1-flash-1017 pour ces deux niveaux.

Rien d'autre n'est touche : ni les statuts Bientot, ni l'ordre des fournisseurs, ni les agents.
Gemini reste Bientot : les nouveaux modeles Gemini s'affichent grises avec la mention Bientot
pour tout le monde, sauf pour les adresses de la table acces_anticipe_modeles.

Ne depend pas de la colonne modeles_llm.bientot : fonctionne sur la prod comme sur le staging.
Rejouable sans risque : chaque mise a jour ne vise que l'ancien identifiant, et l'ajout de
Carbon ne fait rien s'il existe deja.
*/

UPDATE public.modeles_llm
SET modele_id = 'claude-fable-5-2', label = 'Claude Fable 5.2', updated_at = now()
WHERE distributeur = 'claude' AND palier = 'premium' AND modele_id = 'claude-fable-5-1';

UPDATE public.modeles_llm
SET modele_id = 'gpt-6.1-terra', label = 'GPT-6.1 Terra', updated_at = now()
WHERE distributeur = 'gpt' AND palier = 'intermediaire' AND modele_id = 'gpt-5.6-terra';

UPDATE public.modeles_llm
SET modele_id = 'gemini-4-hydrogen', label = 'Gemini 4 Hydrogen', updated_at = now()
WHERE distributeur = 'gemini' AND palier = 'avance' AND modele_id = 'gemini-3.8-flash';

INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label)
VALUES ('gemini', 'premium', 5, 'gemini-4-carbon', 'Gemini 4 Carbon')
ON CONFLICT (distributeur, palier) DO NOTHING;

UPDATE public.modeles_llm
SET label = 'DeepSeek V4.1 Flash', updated_at = now()
WHERE distributeur = 'deepseek' AND modele_id = 'deepseek-v4-flash' AND label <> 'DeepSeek V4.1 Flash';
