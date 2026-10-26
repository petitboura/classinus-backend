/*
Pont fichiers joints -> montage vidéo (26/10/2026, demande Bourama) : déclare le nouvel
outil video_importer_fichier_conversation du serveur « video » comme disponible côté
plateforme, comme video_lister_outils et video_executer_outil (2026_10_24).
Il fait partie de la catégorie montage_video : le modèle le réclame avec les deux autres
via demander_outils. À appliquer APRÈS le déploiement du code qui contient l'outil.
Pour désactiver : UPDATE registre_outils_plateforme SET disponible = false WHERE nom_outil = 'video_importer_fichier_conversation';
*/
INSERT INTO registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
VALUES ('video_importer_fichier_conversation', 1, 'video', true, now())
ON CONFLICT (nom_outil) DO UPDATE SET disponible = true, updated_at = now();
