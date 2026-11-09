/*
  Classinus : deblocage du telechargement d'une image apres un partage termine.

  partage_termine_a : date a laquelle l'appli a signale que l'utilisateur a
  termine le geste de partage pour cette generation. NULL = pas encore partagee.
  Ne concerne que les images : la video n'est jamais verrouillee.

  La colonne vit sur la ligne de higgsfield_generations, deja couverte par
  ON DELETE CASCADE vers auth.users, la purge du compte et l'export.
*/
alter table public.higgsfield_generations
  add column if not exists partage_termine_a timestamptz;
