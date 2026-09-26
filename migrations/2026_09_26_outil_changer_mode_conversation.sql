-- 26/09/2026, demande Bourama : declare changer_mode_conversation comme
-- disponible cote plateforme, meme mecanisme que les outils precedents
-- (voir migrations/2026_09_24_outil_lire_reponses_qcm.sql) -- sans cette
-- ligne l'outil existe dans le code (core/outils_changement_mode.py) mais
-- n'est jamais propose au modele/routeur (voir
-- core/mcp_tools.py::_outils_generation_disponibles), ce qui expliquait
-- que le modele "ne trouve pas l'outil" malgre son enregistrement MCP et
-- son forcage dans core/main.py (outils_forces_contexte).
-- Le catalogue d'outils est mis en cache 24h cote serveur : un
-- redemarrage du service Railway le prend en compte tout de suite.

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('changer_mode_conversation', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
