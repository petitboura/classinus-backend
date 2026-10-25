/*
Renommage de l'outil gerer_comportement en gerer_configuration (25/10/2026, demande
Bourama). L'outil ne gère plus que la configuration de l'utilisateur (règles, style,
procédures, comportements) ; les skills passent uniquement par gerer_skill.
Même mécanisme que les autres outils : sans cette ligne, le nouvel outil existe dans le
code mais n'est jamais proposé au modèle (voir core/mcp_tools.py,
lister_outils_autorises_pour_agent).
Le cache des outils dure 24h : redéployer le backend (ou forcer_rechargement_catalogue_outils).
À appliquer APRÈS le déploiement du code qui contient gerer_configuration.
*/

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('gerer_configuration', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();

delete from registre_outils_plateforme where nom_outil = 'gerer_comportement';
