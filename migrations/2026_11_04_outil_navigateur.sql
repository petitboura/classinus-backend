/*
Outil navigateur à part de l'exécution de code (demande Bourama, 04/11/2026).
Déclare le serveur « navigateur » (outil gerer_navigateur) comme disponible côté plateforme : le modèle
le réclame via demander_outils (catégorie navigateur). Le navigateur n'est réellement proposé que si
les boîtes Docker sont configurées (EXECUTION_CODE_FOURNISSEUR=docker, BOITES_URL, BOITES_TOKEN).
Pour désactiver : UPDATE public.registre_outils_plateforme SET disponible = false WHERE nom_serveur = 'navigateur';
*/
INSERT INTO public.registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
VALUES ('gerer_navigateur', 1, 'navigateur', true, now())
ON CONFLICT (nom_outil) DO UPDATE SET
    categorie = EXCLUDED.categorie,
    nom_serveur = EXCLUDED.nom_serveur,
    disponible = true,
    updated_at = now();
