/*
Limites de téléchargement du bac à sable pour les documents Office (02/11/2026).

FACULTATIVE et indépendante de la migration des skills officiels. À appliquer sur le Supabase de
staging d'abord, puis seulement si Bourama le décide pour la production.

Pourquoi : par défaut le bac à sable ne livre que 1 Mo par fichier (max_file_bytes) et 5 Mo au
total (max_download_bytes). Une présentation avec quelques images dépasse vite 1 Mo et serait refusée.
max_file_bytes borne aussi la taille d'un script envoyé au bac à sable, c'est donc la valeur la plus
sensible : la relever ne coûte rien en temps d'exécution, mais agrandit ce que le modèle peut y envoyer.

Valeurs proposées : 10 Mo par fichier, 25 Mo au total. Les temps d'exécution et les quotas de minutes
par jour et par mois ne changent pas (le coût d'E2B dépend du temps, pas de la taille des fichiers).
Pour revenir en arrière : remettre 1048576 et 5000000.
*/
UPDATE public.execution_code_configuration
SET max_file_bytes = 10485760,
    max_download_bytes = 26214400,
    updated_at = now()
WHERE id = true;
