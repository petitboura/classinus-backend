/*
Travail sur les documents joints (21/11/2026, demande Bourama) : déclare cinq nouveaux outils
comme disponibles côté plateforme, même mécanisme que lire_document_conversation
(2026_10_27). Sans ces lignes, les outils existent dans le code
(core/outils_travail_documents.py) mais ne sont jamais proposés au modèle.

- modifier_document_conversation : modifier un Word, Excel ou PowerPoint joint
- fusionner_pdf, decouper_pdf, tourner_pages_pdf, remplir_formulaire_pdf : travail sur des PDF joints

Le cache des outils dure 24h : un redéploiement du backend (ou
forcer_rechargement_catalogue_outils) est nécessaire pour qu'ils apparaissent sans attendre.
À appliquer APRÈS le déploiement du code qui contient les outils, d'abord sur la base de staging.
Pour désactiver un outil :
update registre_outils_plateforme set disponible = false where nom_outil = 'fusionner_pdf';
*/

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
    ('modifier_document_conversation', 1, 'generation', true, now()),
    ('fusionner_pdf', 1, 'generation', true, now()),
    ('decouper_pdf', 1, 'generation', true, now()),
    ('tourner_pages_pdf', 1, 'generation', true, now()),
    ('remplir_formulaire_pdf', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
