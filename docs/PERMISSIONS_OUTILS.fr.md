# Permissions des outils

[English version](PERMISSIONS_OUTILS.md) · [Français]

Réglages par personne qui décident ce qui se passe quand l'IA veut utiliser un outil d'une application connectée ou d'un serveur MCP personnalisé. Ajoutés le 25 novembre 2026 (branche `feat/permissions-outils`).

## Les états

- **autoriser** : l'outil s'exécute sans rien demander.
- **demander** : la personne confirme à chaque fois (la carte de confirmation du chat).
- **bloquer** : l'outil n'est pas lancé. L'IA reçoit un refus clair (français et anglais, `TEXTE_OUTIL_BLOQUE`) et explique que l'outil est bloqué et où le réactiver.

## Catégories et priorité

Chaque application a deux catégories : `lecture` (lecture seule) et `ecriture` (écrit ou supprime). Un réglage se pose sur une catégorie ou sur un outil. Ordre de priorité : l'outil, puis la catégorie, puis la valeur par défaut.

Les valeurs par défaut sont celles d'avant la fonction : application connectée = lecture autorisée, écriture à confirmer ; serveur MCP perso = tout à confirmer. Les actions de `AUTORISATION_PERMANENTE_INTERDITE` ne peuvent jamais être `autoriser`.

Un groupe est le nom de l'application (`notion`, `vercel_mcp`...) ou `custommcp_<6 caractères hexadécimaux de l'identifiant du serveur>`. Une clé de catégorie est `categorie:<groupe>:<lecture|ecriture>`.

## Stockage

Table `permissions_outils` (`user_id`, `cle`, `etat`, `nom_lisible`, dates), RLS actif, `ON DELETE CASCADE` vers `auth.users`. Seuls les réglages explicites sont stockés. Migration : `migrations/2026_11_24_permissions_outils.sql` (elle reprend aussi les anciennes lignes « Toujours autoriser » et l'ancien réglage des serveurs perso, conservés mais plus lus). La table est dans `core/purge_compte.py` et dans l'export des données.

## Code

- `core/permissions_outils.py` : logique pure et accès à la base.
- `core/catalogue_permissions.py` : liste les outils d'une application et les classe (lecture ou écriture).
- `core/execution_outils.py` : `etat_permission_appel` applique le réglage dans le chat ; un appel bloqué est refusé avant exécution.
- `api/widgets_outils.py` : même règle pour les appels venant d'un widget (`OUTIL_BLOQUE`, HTTP 403).
- `core/autorisations_outils.py` : le bouton « Toujours autoriser » du chat écrit `autoriser`.

## API

- `GET /api/permissions-outils/{groupe}` : deux catégories, chacune avec son réglage (`etat`, `etat_effectif`, `par_defaut`) et ses outils.
- `PUT /api/permissions-outils/{groupe}` avec `{"cle": ..., "etat": "autoriser" | "demander" | "bloquer" | null}` ; `null` retire le réglage. Le groupe d'un serveur perso doit appartenir à l'appelant.
- Les anciennes routes `/api/autorisations-outils` et `/api/mcp-personnalises/{id}/autorisation-non-sensibles` fonctionnent toujours.

Codes d'erreur (français et anglais dans `core/erreurs.py` et `lib/erreurs.ts`) : `OUTIL_BLOQUE`, `PERMISSIONS_OUTILS_*`.

## Tests

`python3 -m pytest test_permissions_outils.py test_permissions_outils_execution.py test_catalogue_permissions.py` (hors ligne).
