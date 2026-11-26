/*
Messages et questions pendant que Classinus travaille (25/11/2026, demande Bourama).

1. Déclare l'outil poser_question comme disponible côté plateforme, même mécanisme que
   dire_a_l_etudiant et lire_document_conversation. Sans cette ligne, l'outil existe dans le
   code (core/outils_question.py) mais n'est jamais proposé au modèle.
2. Ajoute le réglage du délai d'attente d'une question bloquante dans parametres_outils :
   delai_reponse_question_secondes, 600 secondes (10 minutes) au départ. Le code le ramène entre
   30 secondes et 840 secondes (Railway coupe une requête HTTP à 15 minutes, voir
   core/questions_utilisateur.py). Pour le changer, sans toucher au code :
   update parametres_outils set valeur = 300, updated_at = now() where cle = 'delai_reponse_question_secondes';

Aucune donnée liée à un compte : rien à ajouter à la purge de compte ni à l'export.

Le cache des outils et des réglages dure 24h : un redéploiement du backend (ou
forcer_rechargement_catalogue_outils) est nécessaire pour les prendre en compte sans attendre.
À appliquer APRÈS le déploiement du code qui contient l'outil, d'abord sur la base de staging.
Pour désactiver l'outil :
update registre_outils_plateforme set disponible = false where nom_outil = 'poser_question';
*/

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('poser_question', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();

insert into parametres_outils (cle, valeur, updated_at)
values ('delai_reponse_question_secondes', 600, now())
on conflict (cle) do nothing;
