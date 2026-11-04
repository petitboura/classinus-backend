> [English version](./DEPLOIEMENT.md) · **Version française**

# Déploiement du backend

## Déploiement de l’API

La configuration de production documentée dans ce dépôt utilise Railway et Railpack :

- `Procfile` définit la commande Uvicorn de l’API.
- `railpack.json` décrit les paquets système nécessaires.
- `requirements.txt` contient les dépendances Python.
- `api/main.py` est le point d’entrée FastAPI.

La checklist opérationnelle et la liste des variables sont maintenues dans [`RAILWAY_DEPLOY.md`](../RAILWAY_DEPLOY.md). La consulter avant chaque changement de service ou de configuration, puis comparer avec le tableau de bord Railway : ce document décrit une configuration relevée à une date donnée, pas un accès live à l’infrastructure.

## Service de montage vidéo

Le dépôt contient aussi `api/main_montage.py` et `Dockerfile.montage` pour le service de montage séparé. Le backend principal peut lui déléguer le montage lorsque `MONTAGE_VIDEO_URL` est configurée. Les paramètres dédiés et variables de ce service sont décrits dans `RAILWAY_DEPLOY.md`.

## Docker et environnements de test

Le `Dockerfile` racine décrit une construction Docker distincte de la construction Railpack. Ses commentaires indiquent notamment son emploi pour des builds Docker et des environnements de test. Ne pas supposer qu’un fichier Docker est utilisé par le déploiement Railway principal : vérifier le réglage de construction du service concerné.

## Checklist avant déploiement

1. Vérifier la branche et le commit à déployer.
2. Vérifier les variables de l’environnement ciblé, sans recopier de secrets dans Git.
3. Appliquer les migrations Supabase requises avant d’activer le code correspondant.
4. Vérifier les services externes et les URLs OAuth de retour.
5. Contrôler le build, les logs de démarrage et `/health`.
6. Tester les fonctionnalités sensibles sur l’environnement de destination.

Un retour arrière du code ne restaure pas automatiquement la base de données. Vérifier séparément la compatibilité des migrations.
