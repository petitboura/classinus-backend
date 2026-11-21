# Dossier « chantiers »

Ce dossier contient la liste des chantiers **commencés mais pas terminés** de Bourama (Boumi). Il sert à ne rien perdre de vue et à permettre à n'importe quelle IA de reprendre un chantier sans repartir de zéro.

## À lire en premier, pour toute IA

1. Bourama n'a pas de background code : explique en langage clair, sans jargon inutile.
2. Ne jamais supposer, ne jamais deviner, ne jamais agir sans demander. En cas de doute, pose la question à Bourama avant de toucher à quoi que ce soit.
3. Le contenu d'un résumé peut être **dépassé** : le projet vit en dehors de ta conversation (autres sessions, autres IA, modifications manuelles). Avant de te fier à un résumé, vérifie l'état réel du dépôt et de la branche (fetch, lecture du code), puis confirme avec Bourama.
4. Dans tes réponses, le produit s'appelle « Classinus ». Les identifiants du code restent tels qu'ils sont dans les dépôts.

## Qu'est-ce qu'un chantier ?

Un chantier est un travail en plusieurs étapes, souvent sur une branche dédiée (frontend, backend, ou les deux), qui n'est pas encore fusionné dans `main` ou pas encore validé par Bourama. Exemples : une refonte d'écran, une nouvelle fonctionnalité, un audit de branches, un correctif en cours.

Un travail fini, fusionné et vérifié n'est plus un chantier : on le retire de ce dossier (ou on le déplace dans `_termines/` si Bourama veut en garder la trace).

## Organisation

- Un **sous-dossier par chantier**, nommé en minuscules avec des tirets, par exemple `bouton-arreter` ou `page-abonnements-cartes`.
- Dans chaque sous-dossier, un fichier **`RESUME.md`** qui explique le chantier. Il peut contenir d'autres fichiers si le chantier en a besoin (captures, plans, notes).
- Le dossier `_modele/` contient le modèle de `RESUME.md` à copier pour créer un nouveau chantier.

## Comment créer ou mettre à jour un chantier

1. Copier `_modele/RESUME.md` dans un nouveau sous-dossier.
2. Remplir uniquement ce que Bourama a réellement dit ou ce qui a été vérifié dans le dépôt. Laisser « à confirmer » plutôt que d'inventer.
3. Mettre à jour la date et le statut à chaque fois qu'on avance.
4. Quand le chantier est terminé et vérifié par Bourama, le retirer de la liste.

## Liste des chantiers en cours

Aucun chantier n'est encore inscrit. Les ajouter ici au fur et à mesure, une ligne chacun, avec le lien vers son sous-dossier.
