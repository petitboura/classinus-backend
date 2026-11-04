> [English version](./DEVELOPPEMENT.md) · **Version française**

# Développement du backend

## Prérequis

- Python et pip.
- Un projet Supabase dédié à l’environnement de travail.
- Les clés des services nécessaires à la fonctionnalité testée.

## Installer les dépendances

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

## Variables d’environnement

Le dépôt n’utilise pas un fichier d’exemple unique pour toutes les intégrations. Configurer les valeurs dans l’environnement local, sans les committer.

Pour démarrer le service, les variables centrales sont `SUPABASE_URL`, `SUPABASE_SECRET`, `GROQ_API_KEY` et `GOOGLE_API_KEY`. Les fournisseurs, connexions OAuth, notifications et services multimédias ajoutent leurs propres variables. Consulter [RAILWAY_DEPLOY.md](./deployment/RAILWAY_DEPLOY.md) et le code du module concerné.

## Démarrer l’API

```bash
uvicorn api.main:app --reload --port 8000
```

Vérifier [http://localhost:8000/health](http://localhost:8000/health).

## Tests et vérifications

Les tests sont répartis entre `tests/` et les fichiers `test_*.py` à la racine. Exécuter le test correspondant au domaine modifié, puis les tests de non-régression pertinents.

La préparation avant déploiement dispose d’un script dédié :

```bash
python scripts/predeploiement.py
```

Ce script effectue les opérations de pré-déploiement qui lui sont configurées, dont la synchronisation des skills officiels et une vérification Gemini Live. Il ne remplace pas les tests complets ni la validation des migrations.

## Modifier le schéma

Les changements PostgreSQL doivent être décrits dans un fichier SQL versionné sous `migrations/`. Appliquer la migration sur l’environnement ciblé, puis vérifier le comportement des routes et des règles RLS avant de déployer le code qui en dépend.
