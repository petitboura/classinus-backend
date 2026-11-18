/*
  Groupe de chaque modele, de 1 a 5 (17/11/2026, demande de Bourama).
  1 = frontiere (badge Max), 2 a 4 = autres modeles a credit (verrou), 5 = tres bon marche, hors credit.
  Placements a valider : Muse Spark 1.3 (groupe 3 propose, 2 cite), GPT-6 Luna (4 propose, 5 possible),
  Gemini 4 Hydrogen (3) et Grok 4.3 (3) en attendant leurs remplacants. Muse Spark Open n'a pas de groupe.
  Le mot "Bientot" est remplace par un verrou : le texte de la cle bientot devient l'info-bulle du verrou.
*/
alter table public.modeles_llm
  add column if not exists groupe smallint check (groupe between 1 and 5);

update public.modeles_llm set groupe = case modele_id
  when 'claude-fable-5-2' then 1
  when 'gpt-6-astra' then 1
  when 'muse-wonder-1.0' then 1
  when 'gemini-4-carbon' then 1
  when 'claude-opus-5-5' then 2
  when 'gpt-6.1-sol' then 2
  when 'gemini-4-argon' then 2
  when 'grok-4.7' then 2
  when 'deepseek-v4-pro' then 2
  when 'claude-sonnet-5-5' then 3
  when 'gpt-6.1-terra' then 3
  when 'gemini-4-hydrogen' then 3
  when 'grok-4.3' then 3
  when 'muse-spark-1.3' then 3
  when 'claude-haiku-5-5' then 4
  when 'gpt-6-luna' then 4
  when 'gemini-3.5-flash-lite' then 4
  when 'grok-build-0.1' then 4
  when 'glm-5.3' then 4
  when 'qwen3.8-27b' then 4
  when 'deepseek-v4-flash' then 5
  when 'glm-5.3-flash' then 5
  when 'qwen3.8-flash-next' then 5
  when 'muse-glimmer-30b' then 5
  when 'nemotron-nano-omni-30b-a3b-reasoning' then 5
  else groupe end;

insert into public.textes_modeles_llm (cle, langue, texte) values
  ('bientot', 'fr', 'Disponible avec un abonnement'),
  ('bientot', 'en', 'Available with a plan'),
  ('badge_groupe_1', 'fr', 'Max'),
  ('badge_groupe_1', 'en', 'Max')
on conflict (cle, langue) do update set texte = excluded.texte, updated_at = now();
