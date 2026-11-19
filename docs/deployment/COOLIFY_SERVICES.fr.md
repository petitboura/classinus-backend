# Raccordement des services Classinus sur Coolify

[English version](./COOLIFY_SERVICES.md) · **Version française**

Ce guide décrit les connexions entre le backend Classinus et les trois services spécialisés exposés sur Coolify.

## Adresses de production

| Service | URL | Endpoint utilisé |
|---|---|---|
| Class-Tech | https://classtech.classinus.com | `/mcp/diagnostic` |
| Montage vidéo | https://montage.classinus.com | `/mcp/video/` |
| Boîtes Docker Vultr | https://boites.classinus.com | API HTTP `/boites` et `/navigateurs` |

Le frontend appelle uniquement le backend Classinus. Les trois services ne doivent pas être appelés directement par le navigateur.

## 1. Variables à définir sur le service backend Classinus

Dans Coolify, ouvrir le service du backend, puis **Environment Variables** :

```env
CLASSTECH_URL_MCP=https://classtech.classinus.com/mcp/diagnostic
MONTAGE_VIDEO_URL=https://montage.classinus.com
BOITES_URL=https://boites.classinus.com
BOITES_TOKEN=<même-secret-long-que-sur-boites-service>
```

Ne jamais mettre de valeur secrète dans Git ou dans le frontend.

`EXECUTION_CODE_FOURNISSEUR=docker` est une variable d'activation séparée : `EXECUTION_CODE_FOURNISSEUR=docker` à ajouter seulement après avoir vérifié le service, son domaine HTTPS, son jeton et les tests de bout en bout. Elle remplace alors E2B par les boîtes Docker Vultr pour l'exécution de code et du navigateur. Tant que cette variable vaut `e2b` ou est absente, E2B reste utilisé.

Class-Tech a aussi ce domaine comme valeur par défaut dans le code. Garder néanmoins `CLASSTECH_URL_MCP` explicite dans Coolify pour rendre la configuration de production visible.

Sur le backend principal, définir également `R2_PUBLIC_BASE_URL=https://<domaine-public-du-backend>` si cette variable n'est pas déjà configurée. Elle doit désigner le domaine de l'API Classinus qui sert `/fichiers/r2/...`, et non `montage.classinus.com`.

## 2. Service Class-Tech

Dans le service Class-Tech sur Coolify :

- Domaine public : `classtech.classinus.com`.
- Variable obligatoire `MCP_HOTE_PUBLIC` : `classtech.classinus.com` (hôte seul, sans protocole ni chemin), pour la protection anti-rebond DNS du serveur.
- Endpoint MCP appelé par le backend : `https://classtech.classinus.com/mcp/diagnostic`.
- Endpoint de santé utilisé pour le réveil : `https://classtech.classinus.com/health`.

Le registre du backend envoie les outils de diagnostic vers ce serveur. Les outils qui nécessitent l'application PC continuent de passer par le relais applicatif ; ils ne sont pas exécutés sur le serveur Class-Tech.

## 3. Service de montage vidéo

Dans le service de montage Coolify :

- Construire avec le fichier `Dockerfile.montage` à la racine du dépôt.
- Commande de démarrage déjà définie dans l'image : `uvicorn api.main_montage:app --host 0.0.0.0 --port ${PORT:-8000}`.
- Port interne à exposer dans Coolify : `8000`.
- Domaine public : `montage.classinus.com`.
- Variables requises : `SUPABASE_URL`, `SUPABASE_SECRET`, `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`.
- `SUPABASE_SECRET` doit être strictement identique à celui du backend principal : il authentifie les appels internes du backend vers la passerelle vidéo.
- Les quatre variables R2 doivent pointer vers le même compte et le même bucket que le backend principal. Ajouter aussi `R2_PUBLIC_BASE_URL` avec l'URL publique de base du backend principal (pas le domaine montage) : les fichiers vidéo publiés renvoient vers la route `/fichiers/r2/...` du backend Classinus.

Le backend construit l'URL MCP complète en ajoutant `/mcp/video/` et les identifiants de l'utilisateur et de la conversation. Ne pas ajouter ce chemin à `MONTAGE_VIDEO_URL`.

Contrôle de santé : `https://montage.classinus.com/sante`.

## 4. Service de boîtes Docker Vultr

Dans la ressource Docker Compose Coolify du service `boites_service` :

- Domaine public : `boites.classinus.com`.
- Port cible du proxy Coolify : port du conteneur API `8080`.
- Le port proxy des boîtes `3128` ne doit jamais être publié sur Internet.
- Le socket Docker reste monté uniquement dans le service `boites-service`.
- Définir `BOITES_TOKEN` dans les variables du service et recopier exactement le même secret dans le backend sous `BOITES_TOKEN`.

Dans le backend, `BOITES_URL` doit être l'URL de base sans chemin : `https://boites.classinus.com`. Le client ajoute lui-même les routes `/boites`, `/navigateurs`, etc.

Contrôle de santé : `https://boites.classinus.com/sante`.

Le service exige un jeton Bearer. Générer un secret long et aléatoire ; ne jamais le réutiliser pour un autre usage. Si les services sont ensuite placés sur un réseau Docker privé partagé, préférer leur adresse interne à l'URL publique, après validation de la résolution DNS et du routage depuis le conteneur backend.

## 5. Ordre de mise en service

1. Déployer Class-Tech et vérifier `/health`.
2. Déployer le service montage avec son Dockerfile dédié, ses variables Supabase et R2, puis vérifier `/sante`.
3. Déployer `boites_service`, vérifier `/sante` et exécuter `boites_service/verifier_serveur.sh` sur le serveur Vultr.
4. Ajouter les variables backend listées plus haut.
5. Redéployer le backend.
6. Vérifier les logs backend : aucun échec de connexion MCP, aucune erreur 401/403 et aucun délai d'attente.
7. Tester un diagnostic Class-Tech, un petit montage vidéo et une exécution de code dans une boîte Docker.
8. Vérifier que le résultat vidéo est bien enregistré dans R2 et accessible depuis Classinus.

## 6. Retour arrière

- Montage vidéo : supprimer `MONTAGE_VIDEO_URL` pour revenir au serveur vidéo intégré au backend.
- Docker : remettre `EXECUTION_CODE_FOURNISSEUR=e2b` ou supprimer la variable pour revenir à E2B. Vérifier que `E2B_API_KEY` est toujours configurée.
- Class-Tech : remplacer `CLASSTECH_URL_MCP` par une autre URL MCP valide.

## Sécurité et limites

Les domaines HTTPS permettent le raccordement sans dépendre d'un nom de conteneur Docker partagé. Pour une configuration définitive sur le même hôte Coolify, un réseau privé commun est préférable lorsque les services peuvent réellement le partager. Dans tous les cas, conserver l'authentification serveur-à-serveur, ne pas exposer le proxy `3128`, et ne jamais transmettre les secrets au frontend.

Les URL fournies identifient les domaines de production déclarés. Leur disponibilité réelle, la configuration du proxy Coolify et les variables déjà présentes dans chaque service doivent encore être contrôlées dans Coolify : ce guide ne prétend pas avoir accès à ces paramètres.
