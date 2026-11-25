# Permissions des outils : autoriser, demander, bloquer

- **Statut** : en cours. Les fondations du backend sont écrites et testées hors ligne sur une branche, la table existe dans Supabase. Les routes, l'interface et plusieurs raccordements ne sont pas faits : la branche n'est pas déployable en l'état.
- **Dernière mise à jour** : 2026-11-25
- **Dépôts concernés** : classinus-backend (branche), Supabase (table créée sur staging et production), classinus-frontend (rien de fait pour cette page, voir plus bas)
- **Branche(s)** : `feat/permissions-outils`, créée à partir de `main` au commit a62fae3, premier commit a1f0858. Aucune branche côté frontend pour l'instant.

## Le but, en langage clair
Bourama veut une page de réglages pour les outils, comme chez Claude : pour chaque outil, trois choix (Autoriser, Demander, Bloquer), regroupés en deux catégories par application (outils en lecture seule, outils qui écrivent ou suppriment). On règle la catégorie entière, puis on peut faire une exception outil par outil. Cela s'ouvre dans le panneau de chaque application (en cliquant sur l'application elle-même) et couvre les serveurs MCP personnalisés et les applications connectées.

## Ce qui est déjà fait
Vérifié dans le dépôt et dans Supabase :
- **Supabase** : table `permissions_outils` créée le 2026-11-24 sur staging (`prchrczmcoqngesbzzfi`) et production (`ljrbwwmiainrjirymmak`), protégée comme l'ancienne (RLS actif, accès réservé au backend), suppression en cascade avec le compte. Reprise des anciennes données : en production 94 autorisations sur 94 reprises, en staging il n'y en avait aucune. Les anciennes tables et la colonne `mcp_personnalises.autoriser_non_sensibles` ne sont pas supprimées (retour en arrière possible). Le fichier de migration est `migrations/2026_11_24_permissions_outils.sql`.
- **Backend, sur la branche** :
  - `core/permissions_outils.py` : priorité outil, puis catégorie, puis valeur par défaut ; validation des réglages ; vue par application. Les valeurs par défaut sont celles d'avant : application connectée = lecture autorisée, écriture à confirmer ; serveur perso = tout à confirmer.
  - `core/execution_outils.py` : un outil bloqué n'est pas lancé et l'IA reçoit un refus clair, en français et en anglais, qu'elle peut expliquer ; une lecture mise sur « Demander » réclame la confirmation ; une écriture peut être autorisée en bloc. Les actions listées dans `AUTORISATION_PERMANENTE_INTERDITE` ne deviennent jamais « autoriser ».
  - `core/autorisations_outils.py` garde ses noms de fonctions mais lit et écrit la nouvelle table.
  - `core/libelles_outils_anglais.py` : le libellé « bloqué » est traduit.
  - 45 tests hors ligne : `test_permissions_outils.py` et `test_permissions_outils_execution.py` (le second fait tourner le vrai `_traiter_appels` avec des doublures pour les dépendances).
- **Frontend (déjà en ligne, hors de ce chantier)** : le 2026-11-24, la case « Toujours autoriser les outils non sensibles » des serveurs perso change tout de suite au clic (commits b962441 sur staging et 54b22fb sur main).

## Ce qui reste à faire
Dans l'ordre :
1. `connexions/mcp_personnalises.py` : `definir_autorisation_non_sensibles`, la création et la modification d'un serveur, et le champ `autoriser_non_sensibles` renvoyé à l'écran doivent lire et écrire la catégorie « lecture » dans la nouvelle table. Tant que ce n'est pas fait, la case des serveurs perso n'a plus d'effet sur cette branche.
2. `api/widgets_outils.py` : appliquer « bloquer » et les catégories (avec `etat_permission_appel`), nouveau code d'erreur `OUTIL_BLOQUE` en français et en anglais (`core/erreurs.py` et `lib/erreurs.ts`).
3. Routes de l'API : une pour lister les outils d'une application avec leurs catégories et leurs états, une pour changer l'état d'une catégorie ou d'un outil. Les outils d'une application connectée viennent du catalogue (`lister_outils_autorises_pour_agent`), ceux d'un serveur perso de sa découverte.
4. Règle de suppression de compte (CLAUDE.md du backend) : ajouter `permissions_outils` à `core/purge_compte.py` et à l'export de `api/profiles.py`.
5. Réécrire les anciens tests qui remplacent `_supabase_memoire` dans `autorisations_outils` : `test_autorisation_permanente_interdite.py`, `test_mcp_perso_autorisation_non_sensibles.py`, et vérifier `test_widgets_appel_outil.py`.
6. Frontend : section « Permissions des outils » dans le panneau de chaque application et de chaque serveur perso (remplace `ActionsToujoursAutorisees`), avec avertissement avant d'autoriser toute l'écriture en bloc, changement instantané, français et anglais, mobile et PC.
7. Documentation en français et en anglais, pages FAQ/AEO.
8. Essai sur le staging, puis fusion après la validation de Bourama.

## Décisions prises par Bourama
- Réglage par catégorie avec exception outil par outil.
- Périmètre : serveurs MCP personnalisés et applications connectées (pas les outils internes de Classinus).
- Emplacement : dans le panneau de l'application, « le clic sur l'appli elle-même ».
- Autoriser toute la catégorie « écriture et suppression » en bloc : oui, avec un avertissement avant d'activer.
- Outil bloqué : refus clair que l'IA peut expliquer (pas de disparition silencieuse).
- Il a dit : « dans la page, pas dans le chat les questions ». Compris comme : ces réglages vivent dans la page de l'application, et la carte de confirmation du chat garde ses boutons actuels.

## Points ouverts
- Confirmer l'interprétation de « pas dans le chat les questions ».
- Les outils internes de Classinus (génération d'image, mémoire, bibliothèque...) ne sont pas dans la page : à confirmer s'il les veut plus tard.

## Pour l'IA qui reprend ce chantier
- Vérifier d'abord la branche `feat/permissions-outils` (fetch, `git log`) : d'autres sessions ont pu avancer.
- Lancer `python3 -m pytest test_permissions_outils.py test_permissions_outils_execution.py` : ils tournent sans réseau. Les autres tests du backend ne tournent pas sans les modules `supabase` et `httpx`.
- Deux chemins d'import coexistent dans le backend (`autorisations_outils` et `core.autorisations_outils` sont deux copies du module). C'est pourquoi `execution_outils.py` reconnaît l'objet de réglages par ses méthodes et non par `isinstance`.
- Ne jamais fusionner `staging` dans `main` sans retirer le bloc « STAGING ONLY » de `next.config.mjs` (frontend).
