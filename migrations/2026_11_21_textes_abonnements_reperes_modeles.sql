/*
  21/11/2026, demande de Bourama (appliquee a la main sur la prod et sur le staging le meme jour).
  Les textes de la page des abonnements ecrivaient encore les noms de modeles a la main (GPT-6 Astra, GPT-6.1 Sol,
  Gemini 4 Argon, Gemini 3.5 Flash-Lite...). Ils prennent maintenant les reperes {modeles:<palier>}, remplis par
  le backend (core/liste_attente.py) depuis la vraie table modeles_llm : la page ne peut plus s'ecarter du classement.
  Idempotente : sans ancienne liste dans le texte, replace() ne change rien.
*/
update public.textes_modeles_llm set
 texte = replace(replace(replace(replace(replace(texte,
   'Claude Fable 5.2, GPT-6 Astra, Gemini 4 Carbon, Muse Wonder', '{modeles:ultra}'),
   'Claude Opus 5.5, GPT-6.1 Sol, Gemini 4 Argon, Grok 4.7, DeepSeek V4 Pro', '{modeles:max}'),
   'Claude Sonnet 5.5, GPT-6.1 Terra, Gemini 4 Hydrogen, Grok 4.3, Muse Spark 1.3', '{modeles:premium}'),
   'Claude Haiku 5.5, GPT-6 Luna, Gemini 3.5 Flash-Lite, Grok Build 0.1, GLM 5.3, Qwen 3.8 27B, DeepSeek V4.1 Flash, Muse Spark Open', '{modeles:pro}'),
   'GLM 5.3 Flash, Qwen 3.8 Flash Next, Muse Glimmer 30B, Nemotron Nano Omni 30B', '{modeles:essentiel}'),
 updated_at = now()
where cle in ('attente_comp_modeles_lignes','attente_palier_10_points','attente_palier_17_points','attente_palier_20_points');
