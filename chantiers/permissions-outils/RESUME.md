# Permissions des outils : autoriser, demander, bloquer

- **Statut** : en cours, presque terminé. Backend et frontend sont écrits sur deux branches. Reste : essai sur staging (rien n'a encore tourné en vrai), vérification du build frontend, validation de Bourama, fusion.
- **Dernière mise à jour** : 2026-11-25
- **Dépôts concernés** : classinus-backend (branche), classinus-frontend (branche), Supabase (table créée sur staging et production)
- **Branche(s)** : backend `feat/permissions-outils` (dernier commit 98f1e5d) ; frontend `feat/permissions-outils` (créée à partir de main au commit 0c3fcbb, un commit : section Permissions des outils). Vercel ne construit pas cette branche : le build n'a pas été vérifié (pas de node_modules ici, seuls les garde-fous `verifier-composants-natifs` et `verifier-couleurs-theme` ont tourné et passent).

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

## Fait depuis (25/11, backend, commit 98f1e5d)
Serveurs perso reliés à la catégorie « lecture » ; `api/widgets_outils.py` applique bloquer et les catégories (`OUTIL_BLOQUE`, 403) ; routes `GET` et `PUT /api/permissions-outils/{groupe}` (`api/permissions_outils.py`, liste des outils dans `core/catalogue_permissions.py`) ; codes d'erreur en français et anglais dans `core/erreurs.py` ; `permissions_outils` dans la purge du compte et l'export ; anciens tests réécrits (ils ne tournent pas ici faute de `fastapi`, `httpx`, `supabase` : à lancer dans un environnement complet) ; documentation `docs/PERMISSIONS_OUTILS.md` et `.fr.md`. 52 tests hors ligne passent.

## Fait depuis (25/11, frontend)
`components/connexions/PermissionsOutils.tsx` : section dans le panneau de chaque application connectée et de chaque serveur perso, trois choix (Autoriser, Demander, Bloquer) par catégorie et par outil, exception outil par outil, avertissement avant d'autoriser toute l'écriture, changement instantané avec retour en arrière si l'enregistrement échoue. Elle remplace la liste « Actions toujours autorisées » et la case « Autoriser d'un coup les outils non sensibles » (panneau et formulaire des serveurs perso). La carte de confirmation du chat et le formulaire d'ajout dans le chat (`FormulaireServeurMcpCarte.tsx`) gardent leur case, qui fonctionne toujours via l'ancienne route. Textes français et anglais, codes d'erreur dans `lib/erreurs.ts`, page publique `/decouvrir/personnaliser/applications-connectees`, docs `docs/PERMISSIONS_OUTILS.md` et `.fr.md`.

## Ce qui reste à faire
1. Vérifier le build du frontend (`npm run build`) dans un environnement complet, et lancer les anciens tests du backend (`test_autorisation_permanente_interdite.py`, `test_mcp_perso_autorisation_non_sensibles.py`, `test_widgets_appel_outil.py`).
2. Essai sur staging : mettre la branche backend et la branche frontend sur staging (Railway et Vercel), ouvrir une application connectée (ex. Notion, Vercel) et un serveur perso, régler, bloquer un outil et vérifier le refus dans le chat et dans un widget.
3. Retouche éventuelle de l'écran selon l'avis de Bourama (voir points ouverts).
4. Fusion après sa validation, jamais `staging` dans `main` sans retirer le bloc « STAGING ONLY ».

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
