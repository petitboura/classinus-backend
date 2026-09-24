-- 24/09/2026, demande Bourama : declare lire_reponses_qcm comme
-- disponible cote plateforme, meme mecanisme que les outils precedents
-- (voir migrations/2026_09_20b_outil_gerer_minuteur.sql). A appliquer
-- APRES le deploiement du code (core/outils_reponses_qcm.py) : sans
-- cette ligne l'outil existe dans le code mais n'est jamais propose au
-- modele/routeur (voir core/mcp_tools.py::_outils_generation_disponibles),
-- ce qui expliquait que le modele "ne trouve pas l'outil" et se rabattait
-- sur le texte brut deja present dans l'historique de la conversation.
-- Le catalogue d'outils est mis en cache 24h cote serveur : un
-- redemarrage du service Railway le prend en compte tout de suite.

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('lire_reponses_qcm', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
