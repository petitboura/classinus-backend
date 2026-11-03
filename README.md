# Classinus — Backend

Le backend de **[Classinus](https://classinus.com)**. Ce dépôt expose l’API FastAPI utilisée par le frontend et héberge les moteurs IA, les outils, les traitements de documents et les services MCP de Classinus.

Le frontend est maintenu séparément : [classinus-frontend](https://github.com/petitboura/classinus-frontend).

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

D’autres variables activent des fournisseurs, connecteurs, notifications et services spécialisés. La liste opérationnelle est tenue dans [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md). Ne jamais publier de valeurs secrètes dans ce dépôt.

## Documentation

| Guide | Contenu |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | organisation de l’API, des moteurs et des services |
| [API](docs/API.md) | domaines fonctionnels et routes |
| [IA et RAG](docs/IA_ET_RAG.md) | fournisseurs, orchestration, embeddings et recherche documentaire |
| [MCP et connecteurs](docs/MCP_ET_CONNECTEURS.md) | serveurs MCP, OAuth et intégrations |
| [Données et sécurité](docs/DONNEES_ET_SECURITE.md) | Supabase, migrations, authentification et secrets |
| [Développement](docs/DEVELOPPEMENT.md) | environnement local, commandes et tests |
| [Déploiement](docs/DEPLOIEMENT.md) | Railpack, Railway et services associés |

## Dépôts liés

- **Frontend :** [petitboura/classinus-frontend](https://github.com/petitboura/classinus-frontend)
- **Backend — ce dépôt :** [petitboura/classinus-backend](https://github.com/petitboura/classinus-backend)
