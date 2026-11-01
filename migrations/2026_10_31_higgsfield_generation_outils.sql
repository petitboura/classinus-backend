-- Moteur Higgsfield interne (Classinus) : 9 outils generation exposes au LLM
-- API d'abord, MCP partage en repli MCP-only. Sans ces lignes,
-- demander_outils(categorie="higgsfield_classinus") rend "rien trouve"
-- meme si le code est pousse (registre_outils_plateforme filtre en base).
insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at) values
  ('lancer_video_higgsfield', 1, 'generation', true, now()),
  ('consulter_video_higgsfield', 1, 'generation', true, now()),
  ('generer_image_higgsfield', 1, 'generation', true, now()),
  ('consulter_image_higgsfield', 1, 'generation', true, now()),
  ('estimer_cout_higgsfield', 1, 'generation', true, now()),
  ('annuler_generation_higgsfield', 1, 'generation', true, now()),
  ('lister_capacites_higgsfield', 1, 'generation', true, now()),
  ('generer_mcp_higgsfield', 1, 'generation', true, now()),
  ('etat_mcp_partage_higgsfield', 1, 'generation', true, now())
on conflict (nom_outil) do update
  set categorie = excluded.categorie,
      nom_serveur = excluded.nom_serveur,
      disponible = true,
      updated_at = now();
