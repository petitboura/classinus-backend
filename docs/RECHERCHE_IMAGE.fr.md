> [English version](./RECHERCHE_IMAGE.md) · **Version française**

# Recherche d'image

L'outil `rechercher_image` (défini dans `core/outils_generation_media.py`) trouve des images qui existent déjà. La recherche elle-même est dans `core/recherche_image.py` : une cascade de fournisseurs suivie d'un cache en mémoire. Elle renvoie une liste de `{"titre", "url", "miniature", "credit"}`, que l'outil renvoie sous la forme `{"images": [...]}`.

Pourquoi une cascade : la première version n'utilisait que Pixabay et Pexels. Ce sont des banques de photos de stock, pas des moteurs de recherche sur le web, donc elles ne trouvaient jamais de vrais lieux, personnes, événements ou schémas de manuels.

## Fournisseurs, dans l'ordre par défaut

| Ordre | Fournisseur | Variable de clé | Ce qu'il apporte |
|---|---|---|---|
| 1 | Wikimedia Commons | aucune | Vraies photos de lieux, personnes, monuments, espèces |
| 2 | Openverse | aucune | Photos et illustrations sous licence libre venues de nombreuses sources |
| 3 | Serper | `SERPER_API_KEY` | Google Images, le vrai web |
| 4 | SerpApi | `SERPAPI_API_KEY` | Google Images, secours de Serper |
| 5 | Pixabay | `PIXABAY_API_KEY` | Photos de stock, illustrations, vecteurs |
| 6 | Pexels | `PEXELS_API_KEY` | Photos de stock, dernier recours |

Un fournisseur n'est essayé que si le précédent a échoué ou n'a rien renvoyé (erreur, quota dépassé, panne, clé absente). Un fournisseur qui demande une clé et n'en a pas est sauté. L'outil n'échoue jamais à cause d'un fournisseur.

Gratuit au moment de l'écriture (7 novembre 2026, à vérifier chez chaque fournisseur avant de compter dessus) : Serper donne 2 500 crédits gratuits une seule fois à l'inscription, qui expirent après 6 mois. SerpApi donne 250 recherches par mois et 50 par heure sur son plan gratuit. Wikimedia Commons et Openverse n'ont pas besoin de clé.

## Réglages (tous facultatifs)

| Variable | Défaut | Effet |
|---|---|---|
| `RECHERCHE_IMAGE_ORDRE` | `wikimedia,openverse,serper,serpapi,pixabay,pexels` | Ordre des fournisseurs, séparés par des virgules. Un fournisseur absent de la liste n'est jamais utilisé. Les noms inconnus sont ignorés. |
| `RECHERCHE_IMAGE_CACHE_SECONDES` | `259200` (3 jours) | Durée du cache. `0` le désactive. |
| `RECHERCHE_IMAGE_CACHE_MAX` | `500` | Nombre maximum de recherches gardées. La plus ancienne est retirée en premier. |

Exemple pour mettre Google Images en premier : `RECHERCHE_IMAGE_ORDRE=serper,serpapi,wikimedia,openverse,pixabay,pexels`.

Wikimedia Commons renvoie presque toujours quelque chose, donc avec l'ordre par défaut les fournisseurs à clé sont rarement atteints. Change l'ordre si tu veux Google Images en premier.

## Cache

Un résultat non vide est gardé en mémoire pour la même requête normalisée (majuscules et espaces en trop ignorés) et le même nombre d'images. Les erreurs et les résultats vides ne sont jamais gardés. Le cache est propre à chaque processus, ce qui suffit car le backend tourne avec un seul processus `uvicorn` (voir `Procfile`). Il est vidé au redémarrage, et `vider_cache_images()` le vide depuis le code.

## Affichage : c'est l'IA qui choisit

Depuis le 8 novembre 2026, rien ne s'affiche automatiquement après une recherche d'image (ni après une recherche de vidéo). L'outil renvoie ses résultats sous la clé `images_trouvees` (et `videos_trouvees` pour les vidéos), que l'affichage automatique ne reconnaît pas. L'IA lit les titres, garde seulement ce qui correspond à la demande, et écrit chaque image en markdown `![titre](url)` à l'endroit de son message où elle en parle. Si aucun résultat ne convient, elle n'en place aucun et le dit.

Ne pas renommer ces clés en `images` ou `videos` : ces noms-là déclenchent l'affichage automatique de tous les résultats, utilisé par les autres outils (captures du navigateur, Higgsfield). Test : `tests/verifier_recherche_media_choix_ia.py`.

## Comportements à connaître

- Seules les adresses `https` sont gardées pour Wikimedia, Openverse, Serper et SerpApi, car une image `http` est bloquée dans une page `https`. Pour Serper et SerpApi, quand l'image d'origine n'est pas en `https`, la miniature (hébergée par Google) est utilisée à la place.
- Le champ `credit` nomme l'auteur ou le site d'origine, et s'affiche en petit dans la galerie. Les images du vrai web ne sont pas forcément libres de droits.
- SerpApi est appelé avec son filtre de contenu sensible activé. Wikimedia Commons et Serper sont appelés sans aucun filtre.
- Certains sites refusent que d'autres pages affichent leurs images. Cela n'a pas encore été mesuré.

## État

Le code et ses tests (`test_recherche_image_cascade.py`) ont été écrits sans accès réseau aux fournisseurs. Les réponses des tests sont fabriquées d'après la documentation des fournisseurs. Le premier vrai essai en production doit confirmer : les formats de réponse, le nombre de crédits qu'une requête Serper consomme, et l'affichage des images dans l'application.

## Mise en place

1. Créer une clé Serper (et éventuellement une clé SerpApi).
2. Ajouter `SERPER_API_KEY` (et `SERPAPI_API_KEY`) dans les variables Railway du service.
3. Redéployer, puis demander à l'assistant une vraie photo (par exemple un monument nommé) et vérifier la galerie et les logs.
