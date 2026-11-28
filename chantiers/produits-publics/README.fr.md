# Chantier : produits publics (backend)

Branche : `feat/produits-publics` (classinus-backend et classinus-frontend, même nom). Demandé par Bourama le 28/11/2026.
Détail complet, décisions et reste à faire : `chantiers/produits-publics/etat.md` dans le dépôt classinus-frontend. Référence technique : [docs/chantiers/produits-publics/README.fr.md](../../docs/chantiers/produits-publics/README.fr.md).

## Décisions (ne pas les rouvrir sans lui demander)

1. Tout compte connecté publie, en ligne tout de suite, sans validation.
2. Images : envoyées par le créateur ET capture automatique du site (les deux).
3. Entrée dans le menu principal de l'appli.
4. Bouton Signaler sur chaque page produit, et retrait par lui (administrateur) : `POST /api/produits-publics/{id}/retirer-admin` ou le traitement des signalements.
5. Page publique du produit rendue côté serveur pour que Google la lise.
6. Travail sur une branche de test, pas dans `main` ; poussé tel quel le 28/11.

## Fait (28/11/2026)

- Table `produits_publics` et colonne `signalements_bibliotheque.produit_public_id`, appliquées sur la base de STAGING seulement (projet prchrczmcoqngesbzzfi).
- Logique, routes, envoi d'images, capture automatique (bureau puis téléphone, chaque requête contrôlée contre les adresses internes), type de signalement, retrait administrateur, purge du compte, export des données, limites dans un seul fichier de réglages.
- 18 tests qui passent (`test_produits_publics.py`), tests i18n qui passent, messages d'erreur français et anglais.
- L'insertion d'un signalement n'envoie plus les champs vides : la table de staging n'a pas les colonnes `type_emplacement` ni `emplacement_id`, donc tout signalement échouait. À vérifier aussi en production.

## À faire

- Appliquer la migration sur la base de PRODUCTION avant le passage dans `main`.
- Tester la capture avec le vrai navigateur du serveur Coolify (jamais testée ici : pas de Chromium dans l'environnement de travail). Vérifier que le navigateur et ses bibliothèques système sont dans l'image, et que la mémoire suffit pour deux captures en même temps.
- Vérifier que le dossier d'images R2 est lisible publiquement et que les adresses d'images fonctionnent pour Google (les images sont servies par l'adresse `get_public_url` du backend).
- Test de bout en bout sur staging : publier, envoyer, capturer, signaler, retirer, supprimer le compte (le dossier R2 doit disparaître).
- Plus tard, possible : clics sur « Visiter », étoiles, catégories (non demandé).
- Reste du frontend : voir `etat.md` du frontend (pages, formulaire, textes anglais, plan du site, pages Découvrir, docs).
