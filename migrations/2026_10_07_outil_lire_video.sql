/*
Lecture du contenu des vidéos YouTube (07/10/2026, demande Bourama, étape 2) :
déclare le nouvel outil lire_video comme disponible côté plateforme, même
mécanisme que rechercher_video (2026_10_06) et rechercher_image (2026_09_01).
Sans cette ligne, l'outil existe dans le code (core/outils_lecture_video.py)
mais n'est jamais proposé au modèle (voir core/mcp_tools.py,
lister_outils_autorises_pour_agent, catégorie 1 = "generation").
Le cache des outils dure 24h : un redéploiement du backend (ou
forcer_rechargement_catalogue_outils) est nécessaire pour que l'outil
apparaisse sans attendre.
À appliquer APRÈS le déploiement du code qui contient l'outil.
*/

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('lire_video', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
