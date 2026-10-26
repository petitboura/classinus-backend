/*
Lecture, à la demande du modèle, d'une vidéo ou d'un audio joint à la conversation
(26/10/2026, demande Bourama) : déclare le nouvel outil lire_media_conversation
comme disponible côté plateforme, même mécanisme que lire_video (2026_10_07).
Sans cette ligne, l'outil existe dans le code (core/outils_lecture_media.py) mais
n'est jamais proposé au modèle.
Le cache des outils dure 24h : un redéploiement du backend (ou
forcer_rechargement_catalogue_outils) est nécessaire pour que l'outil apparaisse
sans attendre. À appliquer APRÈS le déploiement du code qui contient l'outil.
Pour désactiver : update registre_outils_plateforme set disponible = false where nom_outil = 'lire_media_conversation';
*/

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('lire_media_conversation', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
