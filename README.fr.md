> [English version](./README.md) · **Version française**

# Classinus — Backend

Le backend de **[Classinus](https://classinus.com)**. Ce dépôt expose l’API FastAPI utilisée par le frontend et héberge les moteurs IA, les outils, les traitements de documents et les services MCP de Classinus.

Le frontend est maintenu séparément : [classinus-frontend](https://github.com/petitboura/classinus-frontend).

## Hackathon : Vultr Agent Rush (« Blast Radius Zero »)

Les agents Classinus peuvent exécuter du code et piloter un vrai navigateur web. Pour que les dégâts possibles restent à zéro, chacune de ces actions se déroule dans une boîte fermée sur un **serveur Vultr** : quoi que fasse le modèle, ou quoi que tente une page malveillante, rien ne peut atteindre un vrai secret, le réseau interne, ou un site que la personne n'a pas approuvé.

### Services Vultr utilisés

| Service Vultr | Rôle ici |
|---|---|
| **Cloud Compute** (instance `classinus-vultr`, Francfort, 4 vCPU / 8 Go, Ubuntu 24.04) | Centre de contrôle. Fait tourner le service de boîtes ([`boites_service`](boites_service/README.md)) et le backend Classinus, déployés avec **Coolify** (application du marketplace Vultr). |
| **Serverless Inference** (API compatible OpenAI) | Les appels de modèle de l'agent : DeepSeek, GLM, Qwen, Nemotron et Muse, choisis dans le sélecteur de modèles du chat. |
| **Groupe de pare-feu** | Rattaché au serveur pour limiter qui peut joindre le port du service de boîtes. |

### Parcours d'une demande

```
Personne -> chat Classinus -> API backend -> Vultr Serverless Inference (le modèle choisit l'outil)
                                   |
                                   v
                    service de boîtes sur le serveur Vultr
                      |                          |
              boîte de code (Docker)     boîte navigateur (Docker + Chromium/Playwright)
                      \__________________________/
                         proxy de sortie (liste blanche, ports 80/443 seulement)
```

### Confinement (appliqué à chaque boîte)

- Un conteneur Docker par conversation, utilisateur non root, toutes les capacités Linux retirées, `no-new-privileges`, système de fichiers en lecture seule.
- Limites de mémoire, de swap, de processeur, de nombre de processus et de disque ; chaque commande est tuée à la fin de son délai.
- **Aucun secret dans la boîte** : ni clé Classinus, ni clé Vultr. La boîte ne connaît que l'adresse de son proxy.
- Le réseau de la boîte est interne : aucune route vers Internet. Le seul passage est le proxy, domaine par domaine, ports 80 et 443, adresses publiques seulement (ni réseau interne, ni plage de lien local).
- Détruire une boîte supprime son conteneur et son volume ; les boîtes inactives sont mises en pause automatiquement.

Détails et tableau complet : [`boites_service/README.md`](boites_service/README.md).

### Approbation humaine et liste blanche

- L'agent connaît les sites joignables (la liste fait partie de la description de l'outil) et demande l'accès **avant** d'essayer un autre site.
- Une demande de nouveau site affiche une carte de confirmation (« Accès au site ... »). La personne doit confirmer ; il n'existe pas de « toujours autoriser » pour cette action. Les domaines dangereux ou mal formés sont refusés, et le nombre de domaines ajoutés par conversation est plafonné.
- Dans le navigateur, l'action finale (envoyer un formulaire, payer, supprimer, publier) demande aussi l'approbation de la personne avant de s'exécuter.
- Le navigateur renvoie des captures d'écran au modèle de vision pour qu'il vérifie ce qu'il voit ; une page en échec ou vide n'envoie aucune image.

### Essayer (scénario de démonstration)

1. Demande à l'agent : « Ouvre wikipedia.org dans le navigateur. » Wikipedia n'est pas dans la liste blanche : l'agent demande l'accès et tu vois la carte de confirmation.
2. Approuve : la page s'ouvre et l'agent décrit la capture d'écran.
3. Demande-lui de remplir et d'envoyer un formulaire : l'agent le remplit puis attend ton approbation avant l'envoi final. Refuse, et rien ne part.

### Configuration

| Variable | Rôle |
|---|---|
| `VULTR_INFERENCE_API_KEY` | Clé Vultr Serverless Inference |
| `VULTR_INFERENCE_BASE_URL` | Remplacement facultatif de l'adresse d'inférence |
| `EXECUTION_CODE_FOURNISSEUR=docker` | Utiliser les boîtes Vultr à la place de l'ancien fournisseur |
| `BOITES_URL`, `BOITES_TOKEN` | Adresse et jeton du service de boîtes sur le serveur Vultr |

### Limites connues

- Les fichiers d'une boîte vivent en mémoire (tmpfs) : redémarrer le serveur Vultr efface les espaces de travail.
- L'ancien fournisseur de boîtes (E2B) reste activable par configuration pour que la production ne dépende pas d'un seul interrupteur ; si l'inférence Vultr refuse un appel (crédit, quota, clé), l'appel repart par la route habituelle pendant 10 minutes.

## Responsabilités

- API et authentification pour l’application.
- Conversations IA, sélection des fournisseurs et appels d’outils.
- Recherche documentaire et RAG sur les contenus indexés et les bibliothèques.
- Gestion des comptes, de l’historique, des fichiers, des notes, des comportements et des skills.
- Connexions OAuth et intégrations de services externes.
- Services MCP internes et serveurs MCP publics.
- Fonctions multimédias, notifications, voix et canal en direct.

## Architecture technique

FastAPI · Python · Supabase (Auth, PostgreSQL et stockage) · MCP · fournisseurs IA · services de fichiers et de rendu.

Le point d’entrée de l’API est `api/main.py`. Les routes HTTP sont organisées dans `api/`, tandis que la logique métier et les moteurs sont principalement dans `core/`.

## Démarrage local

Prérequis : Python, pip et un projet Supabase configuré pour l’environnement.

Créer et activer un environnement virtuel :

```bash
python -m venv .venv
```

Windows PowerShell :

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux :

```bash
source .venv/bin/activate
```

Installer les dépendances :

```bash
pip install -r requirements.txt
```

Configurer les variables d’environnement nécessaires, puis démarrer l’API :

```bash
uvicorn api.main:app --reload --port 8000
```

Contrôle de santé : [http://localhost:8000/health](http://localhost:8000/health).

## Configuration

Le fonctionnement de base dépend notamment de :

| Variable | Rôle |
|---|---|
| `SUPABASE_URL` | URL du projet Supabase |
| `SUPABASE_SECRET` | secret serveur Supabase, à garder côté backend uniquement |
| `GROQ_API_KEY` | fournisseur IA utilisé par le chemin principal du chat |
| `GOOGLE_API_KEY` | Gemini et vectorisation des contenus |

D’autres variables activent des fournisseurs, connecteurs, notifications et services spécialisés. La liste opérationnelle est tenue dans [docs/deployment/RAILWAY_DEPLOY.md](docs/deployment/RAILWAY_DEPLOY.md). Ne jamais publier de valeurs secrètes dans ce dépôt.

## Documentation

Index complet : [English](docs/README.md) · [Français](docs/README.fr.md).


| Guide | Contenu |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | organisation de l’API, des moteurs et des services |
| [API](docs/API.md) | domaines fonctionnels et routes |
| [IA et RAG](docs/IA_ET_RAG.md) | fournisseurs, orchestration, embeddings et recherche documentaire |
| [MCP et connecteurs](docs/MCP_ET_CONNECTEURS.md) | serveurs MCP, OAuth et intégrations |
| [Données et sécurité](docs/DONNEES_ET_SECURITE.md) | Supabase, migrations, authentification et secrets |
| [Développement](docs/DEVELOPPEMENT.md) | environnement local, commandes et tests |
| [Déploiement](docs/DEPLOIEMENT.md) | Railpack, Railway et services associés |
| [Cartographie technique](docs/CARTOGRAPHIE_TECHNIQUE.md) | inventaire transféré de l’ancien README, référence datée |

## Dépôts liés

- **Frontend :** [petitboura/classinus-frontend](https://github.com/petitboura/classinus-frontend)
- **Backend — ce dépôt :** [petitboura/classinus-backend](https://github.com/petitboura/classinus-backend)
