-- 30/09/2026, demande Bourama : Clovis controle le clavier comme un utilisateur
-- (raccourcis et touches seules, pas seulement du texte). Declare comme
-- disponible l'outil appuyer_touches du canal en direct sur PC, meme
-- mecanisme que migrations/2026_09_28_outils_canal_en_direct_pc.sql.
-- A appliquer APRES le deploiement du code (core/outils_action_agent_pc.py) :
-- sans cette ligne l'outil existe dans le code mais n'est jamais propose au
-- modele (voir core/mcp_tools.py::_outils_generation_disponibles).
-- Le catalogue d'outils est mis en cache 24h cote serveur : un redemarrage
-- du service Railway le prend en compte tout de suite.

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('appuyer_touches', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
