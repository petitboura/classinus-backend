/*
  21/11/2026, demande de Bourama : les textes de la page /abonnements ne gardent plus aucun nom de modele
  ecrit a la main. Chaque liste est remplacee par le repere {modeles:<palier>}, rempli par le serveur avec
  les vrais modeles actifs de modeles_llm (core/liste_attente.py, remplir_reperes_modeles). Francais et anglais.
  Cles : attente_palier_10_points, attente_palier_17_points, attente_palier_20_points, attente_comp_modeles_lignes.
  Idempotente : une fois les listes remplacees, les anciennes chaines n'existent plus.
*/
update public.textes_modeles_llm
   set texte = replace(replace(replace(replace(replace(texte,
     'Claude Fable 5.2, GPT-6 Astra, Gemini 4 Carbon, Muse Wonder', '{modeles:ultra}'),
     'Claude Opus 5.5, GPT-6.1 Sol, Gemini 4 Argon, Grok 4.7, DeepSeek V4 Pro', '{modeles:max}'),
     'Claude Sonnet 5.5, GPT-6.1 Terra, Gemini 4 Hydrogen, Grok 4.3, Muse Spark 1.3', '{modeles:premium}'),
     'Claude Haiku 5.5, GPT-6 Luna, Gemini 3.5 Flash-Lite, Grok Build 0.1, GLM 5.3, Qwen 3.8 27B, DeepSeek V4.1 Flash, Muse Spark Open', '{modeles:pro}'),
     'GLM 5.3 Flash, Qwen 3.8 Flash Next, Muse Glimmer 30B, Nemotron Nano Omni 30B', '{modeles:essentiel}')
 where cle in ('attente_palier_10_points', 'attente_palier_17_points', 'attente_palier_20_points', 'attente_comp_modeles_lignes');
