/*
30/09/2026, demande Bourama : declare comme disponible cote plateforme
l'outil appuyer_touches (Clovis presse une touche seule ou un raccourci
clavier sur le PC de l'etudiant), meme mecanisme que
migrations/2026_09_30_outil_marquer_ecran.sql. A appliquer APRES le
deploiement du code (core/outils_action_agent_pc.py) : sans cette ligne
l'outil existe dans le code mais n'est jamais propose au modele. Le
catalogue est mis en cache 24h cote serveur : un redemarrage du service
Railway le prend en compte tout de suite.
*/
insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('appuyer_touches', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
