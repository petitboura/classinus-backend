> [English version](./API.md) · **Version française**

# API Classinus

## Point d’entrée

L’application FastAPI est créée dans `api/main.py`. Les routes applicatives sont montées sous des routeurs dédiés. Les chemins exacts doivent être vérifiés dans le routeur concerné : ce guide présente les domaines fonctionnels sans recopier une liste de routes qui évolue avec le code.

L’endpoint de santé public est `GET /health`. `GET /health/me` est protégé par l’authentification utilisateur.

## Domaines exposés

| Domaine | Modules principaux |
|---|---|
| Chat et conversations | `api/chat.py`, `api/historique.py`, routes du mode actif, persona et guide |
| Comptes et profils | `api/auth.py`, `api/profiles.py`, `api/agents.py` |
| Fichiers et documents | `api/uploads.py`, `api/fichiers_r2.py`, `api/fichiers_archive.py`, `api/fichiers_externes.py` |
| Bibliothèques | `api/bibliotheque_utilisateur.py`, `api/bibliotheque_publique.py`, dossiers, commentaires, étoiles et compteurs |
| Mémoire, comportements et skills | `api/memoire_eleve.py`, `api/comportements_etudiants.py`, `api/skills.py` |
| Génération et médias | `api/generation.py`, `api/higgsfield.py`, `api/rendu_animation.py`, aperçu de liens |
| Connexions | `api/connexions.py`, `api/connexions_notion.py`, `api/connexions_github.py` |
| Temps réel et appareils | canal temps réel, canal agent applicatif, Gemini Live et appareils mobiles |
| Notifications et rappels | `api/notifications.py`, `api/notifications_push.py`, minuteurs |
| Retours et modération | feedback, signalements et audits |

La liste exacte des routeurs montés est dans la section d’assemblage de `api/main.py`.

## Serveurs MCP

Les services MCP sont exposés sur des chemins distincts de l’API REST. Leur liste et leur mode d’authentification sont décrits dans [MCP et connecteurs](MCP_ET_CONNECTEURS.md).

## Ajouter ou modifier une route

1. Identifier le domaine fonctionnel et le routeur existant dans `api/`.
2. Placer la logique réutilisable dans `core/` plutôt que de concentrer la logique métier dans le routeur.
3. Appliquer l’authentification adaptée à la route et vérifier l’identité à partir du contexte authentifié.
4. Ajouter ou mettre à jour les tests associés.
5. Si la modification touche le schéma Supabase, ajouter une migration SQL dans `migrations/` et la faire appliquer sur l’environnement ciblé avant de dépendre de cette migration.
