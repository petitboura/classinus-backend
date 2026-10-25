/*
Branchement de l'IA aux skills avec dossier (25/10/2026, demande Bourama) : déclare
l'outil gerer_skill comme disponible côté plateforme, même mécanisme que
lire_document_externe (2026_10_10).
Sans cette ligne, l'outil existe dans le code (core/outils_skills.py) mais n'est
jamais proposé au modèle par demander_outils (voir core/mcp_tools.py,
lister_outils_autorises_pour_agent, catégorie 1 = "generation").
Le cache des outils dure 24h : un redéploiement du backend (ou
forcer_rechargement_catalogue_outils) est nécessaire pour que l'outil
apparaisse sans attendre.
À appliquer APRÈS le déploiement du code qui contient l'outil.
*/

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('gerer_skill', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
