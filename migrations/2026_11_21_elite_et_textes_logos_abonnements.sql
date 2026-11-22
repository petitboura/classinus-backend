/*
  21/11/2026, demande de Bourama (appliquee d'abord sur le staging).
  - Le mot « Frontiere » / « Frontier » devient « Elite » dans les cartes de palier et le tableau comparatif.
  - Deux textes pour les logos de la page /abonnements : la ligne sous le titre (entreprises) et le titre du
    bloc des modeles disponibles. Francais et anglais.
  Idempotente.
*/
update public.textes_modeles_llm
   set texte = replace(replace(replace(replace(texte,
     'Modèles de frontière', 'Modèles élite'),
     'Frontière', 'Élite'),
     'Frontier models', 'Elite models'),
     'Frontier', 'Elite'),
       updated_at = now()
 where cle in ('attente_palier_10_points', 'attente_palier_17_points', 'attente_palier_20_points', 'attente_comp_modeles_lignes');

insert into public.textes_modeles_llm (cle, langue, texte) values
  ('attente_entreprises_titre', 'fr', 'Les modèles des grandes entreprises d''IA'),
  ('attente_entreprises_titre', 'en', 'Models from the leading AI companies'),
  ('attente_modeles_titre', 'fr', 'Les modèles disponibles'),
  ('attente_modeles_titre', 'en', 'Available models')
on conflict (cle, langue) do update set texte = excluded.texte, updated_at = now();
