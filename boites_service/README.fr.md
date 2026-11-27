# Service de boîtes (hackathon Vultr)

[English](README.md) · [Français]

Remplace E2B par des boîtes Docker sur le serveur Vultr. Le backend Classinus appelle ce
service par HTTP avec un jeton. Seul ce service touche au socket Docker.

**Une seule boîte par conversation.** Le terminal (code, commandes, fichiers) et le navigateur
Chromium (piloté par Playwright, voir `pilote.py`) vivent dans la même boîte. Le terminal peut donc
lancer une application (`npm run dev`, `python3 -m http.server`) et le navigateur l'ouvre à
`http://localhost:PORT`, sans que rien ne sorte de la boîte.

## Ce qui est imposé à chaque boîte

| Protection | Mise en oeuvre |
| --- | --- |
| Processus isolé | un conteneur Docker par conversation, utilisateur non root (1000), `--cap-drop ALL`, `no-new-privileges`, système de fichiers en lecture seule |
| Limites de mémoire et de processeur | `--memory`, `--memory-swap` (pas de swap), `--cpus`, `--pids-limit` (réglables : BOITES_MEMOIRE 1536m, BOITES_CPUS, BOITES_PIDS 512) |
| Mémoire partagée et /tmp bornés | `--shm-size` (BOITES_SHM 512m) et `/tmp` en tmpfs plafonné (BOITES_TMP 512m), pour Chromium |
| Limite d'espace disque | volume tmpfs plafonné (BOITES_DISQUE) |
| Limite de temps | chaque commande est tuée au bout de son délai (`timeout -k`) |
| Aucun secret dedans | la boîte ne reçoit que les variables du proxy, aucune clé Classinus ni Vultr |
| Réseau fermé par défaut | réseau Docker interne (`internal: true`), aucune route vers Internet |
| Sortie par liste blanche | seul passage : le proxy du service, domaine par domaine, ports 80 et 443, adresses publiques seulement (pas de réseau interne ni de 169.254.x.x) |
| localhost reste dans la boîte | `NO_PROXY=localhost,127.0.0.1,::1` : une application locale ne passe jamais par le proxy |
| Destruction | `DELETE` supprime le conteneur ET son volume ; la pause arrête le conteneur et garde les fichiers |

Limite connue : les fichiers vivent en mémoire (tmpfs) tant que le serveur ne redémarre pas.
Un redémarrage du serveur efface les workspaces.

## Le navigateur dans la boîte

`pilote.py` est copié dans l'image (`/opt/navigateur/pilote.py`). Un petit démon local (127.0.0.1:9333)
garde Chromium ouvert entre deux actions ; chaque action est une commande `python3 pilote.py <action> <json>`
qui renvoie une ligne JSON (page, texte, chemin de la capture).

| Fonction | Réglage (variable du pilote) |
| --- | --- |
| Écran de téléphone ou de bureau | `device` (iphone, android, bureau, nom Playwright) ou `width` et `height`, tactile et ratio de pixels inclus (PILOTE_APPAREIL_IPHONE, PILOTE_APPAREIL_ANDROID) |
| Qualité de la capture | PILOTE_QUALITE (85), PILOTE_ECHELLE (`css` ou `device`) |
| Page entière | PILOTE_HAUTEUR_MAX (4000 pixels) |
| Défilement, attente d'un élément | PILOTE_ATTENTE_MAX_MS (20000) |
| Console et erreurs | PILOTE_CONSOLE_MAX (200 lignes) |
| Fausses réponses réseau | PILOTE_SIMULATIONS_MAX (20), PILOTE_CORPS_MAX (200000) |

## Déploiement sur le serveur Vultr (Coolify)

1. Nouvelle ressource, Docker Compose, dépôt classinus-backend, fichier `boites_service/docker-compose.yml`.
2. Variable obligatoire : `BOITES_TOKEN` (une longue chaîne aléatoire).
3. Déployer. Le service `boite-image` construit l'image des boîtes (avec Chromium, plusieurs minutes la première fois) puis s'arrête, c'est normal.
4. Le service est publié sur le port 8787 du serveur (BOITES_PORT_HOTE pour en changer, le 8080 est pris par Coolify).
   Pare-feu Vultr : n'ouvrir 8787 qu'aux adresses du backend, ou mettre le service derrière HTTPS (domaine Coolify).
   Ne pas ouvrir le port 3128 (proxy) : il n'est destiné qu'au réseau interne des boîtes.
5. Ordre de mise en ligne : reconstruire l'image sur le serveur Vultr D'ABORD, puis déployer le backend.
   Un workspace créé avec l'ancienne image n'a pas le navigateur : l'outil l'explique à l'agent, qui
   télécharge les fichiers, ferme le workspace et en rouvre un nouveau.

## Brancher le backend Classinus

Dans les variables d'environnement du backend (jamais dans le code) :

    EXECUTION_CODE_FOURNISSEUR=docker
    BOITES_URL=https://<adresse du service>
    BOITES_TOKEN=<le même jeton>

Sans `EXECUTION_CODE_FOURNISSEUR=docker`, le backend continue d'utiliser E2B. Pour revenir en arrière :
supprimer la variable ou la remettre à `e2b`. Le navigateur n'existe qu'en mode docker.

## Tests

    python3 -m unittest test_boites_isolees test_boites_service test_navigateur

Les tests sont hors ligne (faux Docker). Le vrai comportement des conteneurs reste à vérifier
sur le serveur : voir `boites_service/verifier_serveur.sh`.
