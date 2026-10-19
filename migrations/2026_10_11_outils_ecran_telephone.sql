-- 11/10/2026, demande Bourama : declare comme disponibles cote plateforme les
-- deux outils de la vision ecran Android (lire_ecran_telephone : Clovis lit le
-- texte de l'ecran du telephone ; marquer_ecran_telephone : il pointe, surligne
-- ou souligne par-dessus les autres applications), meme mecanisme que
-- migrations/2026_09_30_outil_marquer_ecran.sql. A appliquer APRES le
-- deploiement du code (core/outils_action_agent_telephone.py). Le catalogue est
-- mis en cache 24h cote serveur : un redemarrage du service Railway le prend
-- en compte tout de suite.

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('lire_ecran_telephone', 1, 'generation', true, now()),
  ('marquer_ecran_telephone', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
