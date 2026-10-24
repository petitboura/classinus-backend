/*
Montage vidéo disponible sans vidéo jointe (demande Bourama, 24/10/2026).
Déclare les deux outils du serveur « video » comme disponibles côté plateforme : le modèle
les réclame alors via demander_outils (catégorie montage_video). Sans cette ligne, les outils
vidéo restent réservés aux tours où l'éditeur envoie une vidéo.
Pour désactiver : UPDATE public.registre_outils_plateforme SET disponible = false WHERE nom_serveur = 'video';
*/
INSERT INTO public.registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
VALUES
    ('video_lister_outils', 1, 'video', true, now()),
    ('video_executer_outil', 1, 'video', true, now())
ON CONFLICT (nom_outil) DO UPDATE SET
    categorie = EXCLUDED.categorie,
    nom_serveur = EXCLUDED.nom_serveur,
    disponible = true,
    updated_at = now();
