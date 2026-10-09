-- 30/09/2026, demande Bourama : declare comme disponible cote plateforme
-- l'outil marquer_ecran (Clovis entoure, souligne ou surligne un element de
-- l'ecran du PC, avec le moment et la duree qu'il choisit), meme mecanisme
-- que migrations/2026_09_28_outils_canal_en_direct_pc.sql. A appliquer APRES
-- le deploiement du code (core/outils_action_agent_pc.py). Le catalogue est
-- mis en cache 24h cote serveur : un redemarrage du service Railway le prend
-- en compte tout de suite.

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('marquer_ecran', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
