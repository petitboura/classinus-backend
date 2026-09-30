-- 28/09/2026, demande Bourama : declare comme disponibles cote plateforme
-- les outils du canal en direct sur PC (lot S : cliquer_ecran,
-- taper_clavier, ouvrir_application, lire_ecran ; lot U : lire_page),
-- meme mecanisme que les outils precedents (voir
-- migrations/2026_09_20b_outil_gerer_minuteur.sql). A appliquer APRES le
-- deploiement du code (core/outils_action_agent_pc.py et
-- core/outils_action_agent.py) : sans ces lignes les outils existent dans
-- le code mais ne sont jamais proposes au modele/routeur (voir
-- core/mcp_tools.py::_outils_generation_disponibles).
-- Le catalogue d'outils est mis en cache 24h cote serveur : un
-- redemarrage du service Railway les prend en compte tout de suite.

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('pointer_ecran', 1, 'generation', true, now()),
  ('cliquer_ecran', 1, 'generation', true, now()),
  ('taper_clavier', 1, 'generation', true, now()),
  ('ouvrir_application', 1, 'generation', true, now()),
  ('lire_ecran', 1, 'generation', true, now()),
  ('lire_page', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
