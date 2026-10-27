/*
Lecture, à la demande du modèle, d'un document joint à la conversation
(27/10/2026, demande Bourama) : déclare le nouvel outil lire_document_conversation
comme disponible côté plateforme, même mécanisme que lire_media_conversation
(2026_10_26). Sans cette ligne, l'outil existe dans le code
(core/outils_lecture_document.py) mais n'est jamais proposé au modèle.
Le cache des outils dure 24h : un redéploiement du backend (ou
forcer_rechargement_catalogue_outils) est nécessaire pour que l'outil apparaisse
sans attendre. À appliquer APRÈS le déploiement du code qui contient l'outil.
Pour désactiver : update registre_outils_plateforme set disponible = false where nom_outil = 'lire_document_conversation';
*/

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('lire_document_conversation', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
