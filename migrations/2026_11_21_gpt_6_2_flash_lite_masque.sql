/*
  21/11/2026, demande de Bourama (appliquee a la main sur la prod et sur le staging le meme jour).
  - GPT-6.2 Astra et GPT-6.2 Sol remplacent GPT-6 Astra (palier ultra) et GPT-6.1 Sol (palier max).
  - Gemini 3.5 Flash-Lite est masque du panneau (actif = false) ; la ligne reste, reversible.
  Idempotente : la ligne est retrouvee par son palier, pas par son id.
*/
update public.modeles_llm
   set modele_id = 'gpt-6.2-astra', label = 'GPT-6.2 Astra', updated_at = now()
 where distributeur = 'gpt' and palier = 'ultra' and modele_id = 'gpt-6-astra';

update public.modeles_llm
   set modele_id = 'gpt-6.2-sol', label = 'GPT-6.2 Sol', updated_at = now()
 where distributeur = 'gpt' and palier = 'max' and modele_id = 'gpt-6.1-sol';

update public.modeles_llm
   set actif = false, updated_at = now()
 where distributeur = 'gemini' and modele_id = 'gemini-3.5-flash-lite';
