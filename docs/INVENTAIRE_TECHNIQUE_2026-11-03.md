# Cartographie technique du backend

Cette page est une carte de navigation du code. Elle regroupe les modules par responsabilité et indique où commencer selon le type de changement. Les listes exhaustives de fichiers et les notes chronologiques sont volontairement évitées.

## Trouver rapidement le bon endroit

| Besoin | Point de départ |
|---|---|
| Route HTTP | **api/**, puis le routeur concerné |
| Comportement du chat | **api/chat.py**, **core/main.py** |
| Prompt et contexte | **core/construction_system_prompt.py**, **core/configuration.py** |
| Fournisseur IA | **core/fournisseurs_llm.py**, **core/adaptateur_*.py** |
| Outil disponible pour l’IA | **core/registre_outils.py**, **core/mcp_tools.py** |
| Recherche documentaire | **core/embeddings.py**, **core/retriever.py**, **core/bibliotheque_rag.py** |
| Fichiers et stockage | **api/uploads.py**, **core/bibliotheque_fichiers.py**, **core/stockage_r2.py** |
| Connecteur OAuth ou MCP | **connexions/**, **core/serveur_mcp_*.py** |
| Fonction mobile ou temps réel | **api/canal_*.py**, **core/canal_*.py** |
| Traitement vidéo et multimédia | **api/main_montage.py**, **api/rendu_animation.py**, **core/generation_*** |
| Schéma Supabase | **migrations/** |
| Tâche de fond | **api/main.py**, puis le module de la tâche |

## 1. Vue générale

Le parcours type est :

**Frontend Classinus → API FastAPI → routeur du domaine → logique métier dans core/ → Supabase et services externes.**

Le point d’entrée est **api/main.py**. Il crée l’application FastAPI, configure les middlewares, démarre les tâches de cycle de vie et monte les routeurs HTTP ainsi que les transports MCP.

## 2. Les grandes zones du dépôt

| Dossier | Rôle |
|---|---|
| **api/** | points d’entrée HTTP et assemblage de l’application |
| **core/** | logique métier, orchestration IA, outils, RAG, stockage et tâches |
| **connexions/** | OAuth et connexions aux services externes |
| **indexers/** | indexation des documents et contenus |
| **migrations/** | évolutions SQL du schéma Supabase |
| **scripts/** | opérations, synchronisations et contrôles |
| **skills_plateforme/** | skills officiels Classinus |
| **tests/** et fichiers **test_*.py** | tests unitaires et scénarios de non-régression |

## 3. Cycle d’une conversation

1. **Entrée API** — **api/chat.py** reçoit la requête et gère le flux de réponse.
2. **Moteur** — **core/main.py** orchestre le tour de conversation.
3. **Contexte** — **core/construction_system_prompt.py**, **core/historique_conversation.py** et les modules de configuration préparent les informations utiles.
4. **Modèle et outils** — **core/fournisseurs_llm.py**, les adaptateurs et les modules de routage choisissent la génération et les outils autorisés.
5. **Persistance** — **core/persistance_echanges.py** et **core/persistance_tours.py** gèrent l’enregistrement et la continuité des échanges.

Le traitement est découpé en modules. Modifier l’étape concernée dans son module dédié plutôt que de concentrer toute la logique dans le routeur HTTP ou le moteur principal.

## 4. Domaines fonctionnels

### API et comptes

Les routeurs sont dans **api/**. Ils couvrent notamment les profils, l’authentification, le chat, l’historique, les bibliothèques, les fichiers, les comportements, la mémoire, les connexions, les notifications et le temps réel.

Pour ajouter un endpoint, partir du routeur du domaine concerné et placer la logique réutilisable dans **core/**.

### Moteur IA et adaptateurs

- **core/main.py** : orchestration du chat.
- **core/boucle_agent.py** : boucle d’exécution de l’agent.
- **core/construction_system_prompt.py** : préparation du prompt.
- **core/fournisseurs_llm.py** : disponibilité et routage des fournisseurs.
- **core/adaptateur_*.py**, **core/clients_outils_llm.py** : adaptation des API fournisseurs.
- **core/efforts_modeles.py** : niveaux d’effort associés aux modèles.

La disponibilité d’un fournisseur dépend de sa configuration, de ses identifiants et des règles d’accès. Le catalogue des modèles peut évoluer indépendamment du code.

### Outils et autorisations

- **core/registre_outils.py** : catalogue des outils.
- **core/mcp_tools.py** : découverte et appels des outils MCP externes.
- **core/autorisations_outils.py**, **core/execution_outils.py** : autorisations et exécution.
- **core/outils_*.py** : capacités par domaine.

Les opérations sensibles doivent conserver leurs contrôles de confirmation et leurs vérifications côté serveur.

### Documents, bibliothèque et recherche

| Besoin | Modules |
|---|---|
| Embeddings et découpage | **core/embeddings.py** |
| Recherche documentaire du moteur | **core/retriever.py** |
| RAG de la bibliothèque personnelle | **core/bibliotheque_rag.py** |
| RAG du catalogue public | **core/catalogue_public_rag.py** |
| Fichiers et dossiers | **core/bibliotheque_fichiers.py**, **core/dossiers_bibliotheque.py** |
| Indexation PDF et Notion | **indexers/index_documents.py**, **indexers/index_notion.py** |
| Stockage objet | **core/stockage_r2.py** |

Les circuits personnel, public et documentaire ne sont pas interchangeables. Vérifier le propriétaire, la portée, le stockage et la fonction de recherche avant de réutiliser un pipeline.

### Connecteurs et serveurs MCP

Les flux OAuth sont principalement dans **connexions/**. Les serveurs MCP sont implémentés dans **core/serveur_mcp_*.py** et leurs points d’accès sont assemblés dans **api/main.py**.

| Chemin MCP | Service |
|---|---|
| **/mcp/generation** | outils de génération |
| **/mcp/execution-code** | exécution de code |
| **/mcp/video** | outils vidéo |
| **/mcp/github** | outils GitHub |
| **/mcp/netlify** | outils Netlify |
| **/mcp/public** | serveur MCP public documentaire |
| **/mcp/espace** | serveur MCP public de l’espace utilisateur |

Les serveurs publics utilisent une vérification de jeton OAuth dédiée. Ne pas confondre ces points d’accès publics avec les serveurs MCP internes utilisés par le moteur Classinus.

### Mobile, temps réel et PC

Les points de départ sont **api/appareils_mobiles.py**, **api/canal_temps_reel.py**, **api/canal_agent_applicatif.py** et les modules correspondants dans **core/**.

Les actions mobiles différées, l’exploration de dossiers, la lecture d’écran PC et les actions contrôlées sur ordinateur ont des modules distincts. Identifier le canal utilisé avant d’étendre un comportement.

### Multimédia et traitements lourds

La génération de fichiers est répartie dans les modules **core/generation_***. Les traitements vidéo ont aussi des points d’entrée dédiés, dont **api/main_montage.py** et **api/rendu_animation.py**. Le service de montage séparé et ses paramètres sont décrits dans [le guide de déploiement](DEPLOIEMENT.md).

## 5. Données et sécurité

Supabase fournit l’authentification, PostgreSQL et les stockages utilisés par le backend.

- Variables serveur centrales : **SUPABASE_URL** et **SUPABASE_SECRET**.
- Les migrations SQL sont conservées dans **migrations/**.
- Les politiques RLS, contraintes, clés étrangères et fonctions RPC font partie du contrat de chaque fonctionnalité.
- Les secrets des fournisseurs et des connexions OAuth restent dans l’environnement backend.

Toute évolution de schéma doit être livrée avec sa migration, testée sur l’environnement adapté et appliquée avant d’activer le code qui en dépend.

## 6. Tâches de fond

Le cycle de vie FastAPI est piloté depuis **api/main.py**. Des tâches de fond s’occupent notamment de traitements différés, de notifications, de rappels, d’indexation et de synchronisations.

Pour modifier une tâche, localiser son module métier puis vérifier comment elle est démarrée et arrêtée. Éviter de lancer une seconde boucle concurrente sans vérifier le mécanisme existant.

## 7. Tests

Les tests Python sont à la racine et dans **tests/**. Ils couvrent notamment les adaptateurs IA, les flux du chat, les outils et autorisations, les serveurs MCP, les bibliothèques, les documents, les fonctions mobiles et les traitements multimédias.

Lancer les tests liés à la fonctionnalité modifiée, puis les scénarios de non-régression concernés. **python scripts/predeploiement.py** est un contrôle de pré-déploiement ; il ne remplace pas la suite de tests.

## Guides associés

- [Architecture générale](ARCHITECTURE.md)
- [Domaines et routes API](API.md)
- [Fournisseurs IA et RAG](IA_ET_RAG.md)
- [MCP et connecteurs](MCP_ET_CONNECTEURS.md)
- [Données et sécurité](DONNEES_ET_SECURITE.md)
- [Développement local](DEVELOPPEMENT.md)
- [Déploiement](DEPLOIEMENT.md)
- [Checklist Railway](../RAILWAY_DEPLOY.md)
