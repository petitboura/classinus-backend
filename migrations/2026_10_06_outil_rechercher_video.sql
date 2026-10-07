-- Recherche de vidéos YouTube (06/10/2026, demande Bourama) : déclare le nouvel
-- outil rechercher_video comme disponible côté plateforme, même mécanisme que
-- rechercher_image (2026_09_01). Sans cette ligne, l'outil existe dans le code
-- (core/outils_generation_media.py) mais n'est jamais proposé au modèle (voir
-- core/mcp_tools.py::lister_outils_autorises_pour_agent, catégorie 1 =
-- "generation").
-- Appliquée directement en base de production le 06/10, ce fichier sert de
-- trace et de rejouabilité. Le cache des outils dure 24h : un redéploiement du
-- backend (ou forcer_rechargement_catalogue_outils) est nécessaire pour que
-- l'outil apparaisse sans attendre.

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('rechercher_video', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
