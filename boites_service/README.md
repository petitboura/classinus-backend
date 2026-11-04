# Service de boîtes (hackathon Vultr, étape 3)

Remplace E2B par des boîtes Docker sur le serveur Vultr. Le backend Classinus appelle ce
service par HTTP avec un jeton. Seul ce service touche au socket Docker.

## Ce qui est imposé à chaque boîte

| Protection | Mise en oeuvre |
| --- | --- |
| Processus isolé | un conteneur Docker par conversation, utilisateur non root (1000), `--cap-drop ALL`, `no-new-privileges`, système de fichiers en lecture seule |
| Limites de mémoire et de processeur | `--memory`, `--memory-swap` (pas de swap), `--cpus`, `--pids-limit` (réglables : BOITES_MEMOIRE, BOITES_CPUS, BOITES_PIDS) |
| Limite d'espace disque | volume tmpfs plafonné (BOITES_DISQUE) |
| Limite de temps | chaque commande est tuée au bout de son délai (`timeout -k`) |
| Aucun secret dedans | la boîte ne reçoit que les variables du proxy, aucune clé Classinus ni Vultr |
| Réseau fermé par défaut | réseau Docker interne (`internal: true`), aucune route vers Internet |
| Sortie par liste blanche | seul passage : le proxy du service, domaine par domaine, ports 80 et 443, adresses publiques seulement (pas de réseau interne ni de 169.254.x.x) |
| Destruction | `DELETE` supprime le conteneur ET son volume ; la pause arrête le conteneur et garde les fichiers |

Limite connue : les fichiers vivent en mémoire (tmpfs) tant que le serveur ne redémarre pas.
Un redémarrage du serveur efface les workspaces.

## Déploiement sur le serveur Vultr (Coolify)

1. Nouvelle ressource, Docker Compose, dépôt classinus-backend, fichier `boites_service/docker-compose.yml`.
2. Variable obligatoire : `BOITES_TOKEN` (une longue chaîne aléatoire).
3. Déployer. Le service `boite-image` construit l'image des boîtes puis s'arrête, c'est normal.
4. Pare-feu Vultr : n'ouvrir 8080 qu'aux adresses du backend, ou mettre le service derrière HTTPS (domaine Coolify).
   Ne pas ouvrir le port 3128 (proxy) : il n'est destiné qu'au réseau interne des boîtes.

## Brancher le backend Classinus

Dans les variables d'environnement du backend (jamais dans le code) :

    EXECUTION_CODE_FOURNISSEUR=docker
    BOITES_URL=https://<adresse du service>
    BOITES_TOKEN=<le même jeton>

Sans `EXECUTION_CODE_FOURNISSEUR=docker`, le backend continue d'utiliser E2B. Pour revenir en arrière :
supprimer la variable ou la remettre à `e2b`.

## Tests

    python3 -m unittest test_boites_isolees test_boites_service

Les tests sont hors ligne (faux Docker). Le vrai comportement des conteneurs reste à vérifier
sur le serveur : voir `boites_service/verifier_serveur.sh`.
