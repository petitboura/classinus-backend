> [English version](./MCP_ET_CONNECTEURS.md) · **Version française**

# MCP et connecteurs

Classinus utilise MCP à deux niveaux : des serveurs internes consommés par ses propres moteurs, et des serveurs publics auxquels un client externe peut se connecter avec l’identité de l’utilisateur.

## Serveurs MCP exposés par l’API

Les montages sont configurés dans `api/main.py`. Les chemins actuels comprennent :

| Chemin | Fonction |
|---|---|
| `/mcp/generation` | outils de génération utilisés par l’application |
| `/mcp/execution-code` | exécution de code |
| `/mcp/video` | outils vidéo |
| `/mcp/github` | outils GitHub |
| `/mcp/netlify` | outils Netlify |
| `/mcp/public` | serveur MCP public lié aux ressources documentaires |
| `/mcp/espace` | serveur MCP public pour l’espace utilisateur |

Les chemins, transports et paramètres de sécurité doivent être vérifiés dans `api/main.py` et les modules `core/serveur_mcp_*.py`.

## MCP publics et authentification

Les serveurs publics `/mcp/public` et `/mcp/espace` s’appuient sur le mécanisme OAuth de Supabase décrit dans `core/mcp_auth_public.py`. Le jeton présenté par le client externe est vérifié avant d’associer les appels à un compte.

La configuration publique utilise notamment `URL_RESOURCE_SERVER_PUBLIC` et l’URL de retour OAuth. Les réglages OAuth 2.1 / Dynamic Client Registration dans Supabase sont des prérequis opérationnels distincts du code. Vérifier [RAILWAY_DEPLOY.md](./deployment/RAILWAY_DEPLOY.md) et le tableau de bord Supabase avant d’activer une nouvelle instance.

## Connecteurs de comptes

Les routes de connexion sont organisées dans `connexions/` et `api/connexions*`. Les flux de démarrage, d’état et de finalisation OAuth sont gérés par le backend. Les jetons liés aux comptes doivent rester côté serveur et être séparés par utilisateur et fournisseur.

Les fournisseurs référencés dans le code et les migrations comprennent notamment Notion, GitHub, Higgsfield, Vercel, Railway et Supabase. Leur disponibilité dépend de la configuration OAuth et des migrations appliquées.

## Widgets interactifs (MCP-UI et MCP Apps)

Un outil MCP peut venir avec un widget interactif (Higgsfield, par exemple). Le backend le lit dans `core/ressources_ui.py` et l’envoie au frontend par un événement `ressources_ui`, séparément du résultat texte, qui reste le repli. Le frontend l’affiche dans une iframe isolée.

Un serveur peut annoncer un widget de deux façons, et les deux sont gérées :

1. **Dans le résultat de l’outil.** Un bloc de contenu dont l’adresse commence par `ui://`. Si le bloc n’a pas de contenu, le backend le lit avec `resources/read` sur la même session.
2. **Sur la définition de l’outil (MCP Apps).** Le champ `_meta.ui.resourceUri`, renvoyé par `tools/list`, sans bloc `ui://` dans le résultat. Le backend garde cette adresse dans la route de l’outil (`widget_ui_uri`), construite depuis le catalogue en cache, donc sans appel réseau de plus par outil. Après l’appel, il lit le contenu avec `resources/read`. Un bloc `ui://` présent dans le résultat reste prioritaire, et un résultat en erreur n’affiche jamais le widget déclaré.

Règles communes aux deux cas :

- Types affichés : `text/html` (y compris `text/html;profile=mcp-app`) et `text/uri-list`. Les autres types sont ignorés et le texte reste.
- La taille et le nombre de widgets sont bornés (`CLASSINUS_MCP_UI_HTML_MAX_OCTETS`, `CLASSINUS_MCP_UI_MAX_PAR_RESULTAT`) et la lecture du contenu a un délai maximal (`CLASSINUS_MCP_UI_DELAI_LECTURE_SECONDES`).
- La fonction se coupe avec `CLASSINUS_MCP_UI_ACTIF=0`. Sans widget, un résultat d’outil n’est jamais modifié.
- Les serveurs ajoutés par l’utilisateur (`connexions/mcp_personnalises.py`) n’affichent pas encore de widget.
- Le frontend ne laisse un widget qu’ouvrir un lien ou changer sa hauteur. Les appels d’outils depuis un widget sont refusés.

Tests : `test_ressources_ui.py`.

## Ajouter une intégration

1. Étudier le protocole OAuth ou MCP documenté par le fournisseur.
2. Ajouter le flux de connexion et la vérification d’identité dans le backend.
3. Stocker les jetons côté serveur avec une séparation stricte par utilisateur.
4. Ajouter les migrations nécessaires et vérifier les politiques d’accès.
5. Ajouter les tests de connexion, de renouvellement et d’échec.
6. N’exposer l’outil au moteur IA qu’après vérification des autorisations et des opérations sensibles.
