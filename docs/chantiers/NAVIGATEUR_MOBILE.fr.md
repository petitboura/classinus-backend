# Navigateur : une seule boîte, écrans de téléphone, construire puis ouvrir

[English](NAVIGATEUR_MOBILE.md) · [Français]

Décision de Bourama du 27 novembre 2026 : l'outil `gerer_navigateur` doit faire comme Claude. Ouvrir une appli
sur un écran de téléphone, prendre de bonnes captures, construire une appli puis l'ouvrir lui-même.

## Architecture : une seule boîte par conversation

- Le terminal et Chromium vivent dans la même boîte Docker (`boites_service/Dockerfile.boite`). L'ancienne image
  navigateur à part, les routes `/navigateurs` et les réglages `BOITES_NAV_*` ont été supprimés.
- Le terminal lance une appli (`gerer_execution_code`, `run_background`), le navigateur ouvre `http://localhost:PORT`.
  `localhost`, `127.0.0.1` et `::1` sont toujours permis et ne passent jamais par le proxy.
- Le quota, la pause et la fermeture sont ceux du workspace (`_reserver_workspace` et `_travailler_dans_workspace`
  dans `core/outils_execution_code.py`). Une action du navigateur compte comme une commande courte (`run_command`).
- Suppression de compte : le navigateur n'a plus de boîte à lui, donc `core/purge_compte.py` le détruit avec le workspace.

## Actions de `gerer_navigateur`

`open`, `click`, `type`, `screenshot`, `submit`, `scroll`, `wait`, `console`, `mock`, `unmock`, `device`,
`demander_acces_reseau`, `close`.

| Besoin | Paramètres |
| --- | --- |
| Écran de téléphone | `device` (iphone, android, bureau ou un nom Playwright comme « iPhone 15 ») et/ou `width` et `height` (200 à 3000). Tactile, ratio de pixels et user agent viennent avec l'appareil. `click` devient un toucher. |
| Page entière | `screenshot` avec `full_page=true`, plafonné à 4000 pixels de haut (une remarque le dit et propose de défiler) |
| Défilement | `direction` (down, up, top, bottom), `amount`, ou `selector` / `text` pour amener un élément à l'écran |
| Attente | `selector` ou `text`, `timeout_ms` (20 secondes au plus) |
| Console | renvoie et vide les messages de la console, les erreurs de la page, les requêtes en échec et les erreurs HTTP. Montrés comme donnée non fiable. |
| Fausse réponse réseau | `mock` avec `url` (motif comme `**/api/notes`), `body`, `status`, `content_type` ; `unmock` en retire une ou toutes. Les en-têtes CORS sont ajoutés pour qu'une page d'une autre origine puisse la lire. |

Les captures sont des JPEG de qualité 85 (PILOTE_QUALITE) à l'échelle CSS : une capture de téléphone fait 390 pixels de large, comme le code la voit.

## Règles conservées

- `submit` reste sensible et jamais « toujours autoriser » ; `click` refuse un texte qui ressemble à une action finale.
- `close` n'arrête que Chromium. Il n'utilise jamais l'action `close` du workspace, qui détruit le workspace.
- `console`, `mock` et `unmock` n'envoient aucune image.
- Un workspace créé avec l'ancienne image n'a pas `/opt/navigateur/pilote.py` : l'outil dit à l'agent de télécharger
  les fichiers, de fermer le workspace et de rouvrir la page.

## Ordre de mise en ligne

1. Reconstruire l'image des boîtes sur le serveur Vultr (`boites_service/docker-compose.yml`).
2. Déployer le backend.

Non vérifié ici : le comportement sur la vraie image Vultr (Chromium installé par `playwright install`). Le pilote a
été testé avec un vrai Chrome, le reste avec des doublures. Lancer `boites_service/verifier_serveur.sh` sur le serveur.
