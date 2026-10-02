-- 02/10/2026, demande Bourama : declare comme disponibles cote plateforme les
-- outils qui permettent a Clovis d'activer et de desactiver lui-meme le canal
-- en direct depuis le chat (activer_canal_en_direct, desactiver_canal_en_direct,
-- voir core/outils_action_agent.py). Meme mecanisme que
-- migrations/2026_09_28_outils_canal_en_direct_pc.sql : sans ces lignes les
-- outils existent dans le code mais ne sont jamais proposes au modele (voir
-- core/mcp_tools.py::_outils_generation_disponibles).
-- A appliquer APRES le deploiement du code. Le catalogue est mis en cache 24h
-- cote serveur : un redemarrage du service Railway le prend en compte tout de
-- suite. Deja appliquee sur la base de production (projet Clovis).

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('activer_canal_en_direct', 1, 'generation', true, now()),
  ('desactiver_canal_en_direct', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
