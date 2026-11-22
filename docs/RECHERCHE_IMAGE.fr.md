# Recherche d'images

L'outil `rechercher_image` utilise `core/recherche_image.py`. Il interroge
les sources configurées en parallèle, fusionne les résultats, élimine les
doublons et conserve une provenance distincte pour chaque image.

## Sources intégrées

| Source | Clé / variable | Type de contenu |
|---|---|---|
| Wikimedia Commons | Aucune | Photos, lieux, personnes, monuments, espèces |
| Openverse | Aucune | Images et médias sous licences ouvertes |
| Library of Congress | Aucune | Archives et photographies historiques |
| NASA Image and Video Library | Aucune pour l'API de recherche d'images | Espace, Terre, sciences et missions |
| Flickr | `FLICKR_API_KEY` | Photographies publiées par les utilisateurs |
| Smithsonian Open Access | `SMITHSONIAN_API_KEY` | Patrimoine, histoire, art et sciences |
| Europeana | `EUROPEANA_API_KEY` | Collections culturelles et historiques |
| Google Images via Serper | `SERPER_API_KEY` | Images indexées sur le Web |
| Google Images via SerpApi | `SERPAPI_API_KEY` | Images indexées sur le Web |
| Google Images via SearchApi.io | `SEARCHAPI_API_KEY` | Images indexées sur le Web, sources éditeurs et pagination |
| Pixabay | `PIXABAY_API_KEY` | Banque d'images et illustrations |
| Pexels | `PEXELS_API_KEY` | Banque de photographies |

Variables de clés prises en charge :

- `SERPER_API_KEY` : Serper
- `SERPAPI_API_KEY` : SerpApi
- `SEARCHAPI_API_KEY` : SearchApi.io
- `SMITHSONIAN_API_KEY` : Smithsonian Open Access
- `EUROPEANA_API_KEY` : Europeana (envoyée dans le header recommandé `X-Api-Key`)
- `FLICKR_API_KEY` : Flickr
- `PIXABAY_API_KEY` et `PEXELS_API_KEY` : banques d'images, si activées

NASA est interrogé via `images-api.nasa.gov`, l'API publique NASA Image and
Video Library : cette recherche ne demande pas de clé et n'utilise pas
`NASA_API_KEY`. La clé du portail `api.nasa.gov` concerne d'autres API NASA,
pas cet endpoint de recherche d'images.

Une source qui nécessite une clé absente est ignorée. Une panne ou un quota
dépassé sur une source ne bloque pas les autres.

## Recherche, pagination et cache

- Les sources disponibles sont appelées en parallèle, avec un maximum de
  8 appels simultanés.
- Les résultats sont fusionnés en alternant les sources afin qu'une seule
  plateforme ne monopolise pas la première page.
- Les doublons d'URL d'image sont supprimés.
- Une page contient 40 images par défaut. L'outil accepte de 1 à 100 résultats
  par page. La pagination commence à 1.
- Les pages sont mises en cache séparément pendant 3 jours par défaut.
  Variables facultatives : `RECHERCHE_IMAGE_CACHE_SECONDES` et
  `RECHERCHE_IMAGE_CACHE_MAX`.
- `RECHERCHE_IMAGE_ORDRE` permet de choisir l'ordre des sources, séparées par
  des virgules. L'ordre ne change pas le fait qu'elles sont interrogées en
  parallèle ; il sert à stabiliser l'ordre de fusion.

## Provenance de chaque image

Chaque résultat contient :

- `url` : l'adresse de l'image affichée.
- `miniature` : l'adresse de sa version légère quand elle existe.
- `credit` : auteur ou crédit fourni par la source.
- `source_url` : page Web d'origine de l'image, quand la source la fournit.
- `source_name` et `source_domain` : domaine de cette page d'origine.

La page d'origine n'est pas le fournisseur API. Par exemple, une image découverte
avec Google Images peut provenir du site d'un musée, d'un journal ou d'une
institution. L'interface affiche le favicon de ce site et ouvre sa page source.

## Sélection et affichage

L'outil renvoie toujours `images_trouvees`, pas `images`. Rien ne s'affiche
automatiquement : le modèle choisit les images pertinentes et peut demander la
page suivante en rappelant `rechercher_image` avec `page + 1`.

Pour qu'un badge de provenance s'affiche, le modèle doit conserver la page
d'origine dans le titre Markdown :

```markdown
![Titre de l'image](url_de_l_image "url_de_la_page_source")
```

Les images sélectionnées uniquement sont affichées dans une grille responsive.
Les miniatures sont chargées au défilement et le clic conserve l'ouverture dans
la visionneuse intégrée. Le badge de source reste indépendant de l'image et
ouvre directement la page où elle est publiée.

## Affichage progressif (page bambara)

Ajouté le 22 novembre 2026, à la demande de Bourama. Ne vaut que pour la page
bambara (`client` = `page_bambara`) : pour tout autre client, rien ne change.

L'utilisateur de cette page ne sait pas lire, il comprend ce qu'il voit. Avant,
`rechercher_image` attendait la source la plus lente, puis le modèle principal
triait et écrivait ses images : rien n'apparaissait avant la fin. Maintenant :

1. Chaque source répond de son côté. Dès qu'une source a répondu, ses résultats,
   sans les doublons déjà vus (même domaine et même chemin), vont à un petit LLM
   rapide qui choisit ceux qui correspondent vraiment à la demande, par numéro.
2. Les images gardées partent tout de suite à l'écran dans un événement SSE
   `bloc_media`, pendant que les autres sources travaillent encore :
   `{"type": "bloc_media", "id_appel": "...", "genre": "images", "source": "Openverse", "images": [...]}`.
3. À la fin, le modèle principal reçoit un court résumé : combien d'images sont
   déjà à l'écran, leurs titres, et la consigne de ne pas recopier leurs adresses.
   Si le tri d'un lot a échoué (délai dépassé, réponse illisible), ce lot n'est
   pas affiché : il est donné au modèle principal sous `images_trouvees`, comme
   avant, pour qu'il choisisse lui-même.

`page` et `nombre` gardent leur sens : `page` va aux sources (le modèle rappelle
l'outil avec `page=2` pour en voir plus, et le résumé lui suggère
`page_suivante_suggeree`), `nombre` plafonne ce qui est affiché sans jamais
dépasser le réglage `MEDIAS_PROGRESSIFS_MAX_IMAGES`. Une valeur invalide revient
au défaut.

Le petit LLM désigne les résultats par numéro et c'est le code qui écrit les
adresses : un LLM qui recopie une longue adresse se trompe parfois d'un caractère,
et une image cassée ne se voit pas sur une page sans texte.

Pourquoi un canal : les outils passent par un client MCP réseau, donc un fil
d'outil ne peut pas écrire directement dans le flux de la réponse.
`core/medias_progressifs.py` fournit une file (`CanalMedias`) que la boucle de
`core/execution_outils.py` vide toutes les 0,05 s pendant qu'elle attend les
outils, pour envoyer chaque bloc avant le résultat de l'outil. La page bambara
marque les routes de `rechercher_image` et `rechercher_video` dans
`core/outils_page_bambara.py` (clé `medias_progressifs`).

Réglages, tous facultatifs (variables d'environnement du backend) :

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `MEDIAS_PROGRESSIFS_MODELE` | `openai/gpt-oss-20b` | modèle Groq du tri |
| `MEDIAS_PROGRESSIFS_DELAI_LLM_SECONDES` | 8 | délai d'un tri |
| `MEDIAS_PROGRESSIFS_LLM_PARALLELES` | 6 | tris simultanés au plus |
| `MEDIAS_PROGRESSIFS_PAR_SOURCE` | 12 | images demandées à chaque source |
| `MEDIAS_PROGRESSIFS_MAX_IMAGES` | 60 | images affichées au plus |
| `MEDIAS_PROGRESSIFS_MAX_VIDEOS` | 30 | vidéos affichées au plus |
| `MEDIAS_PROGRESSIFS_DELAI_SECONDES` | 25 | durée maximale de toute la recherche |

Le modèle par défaut est déjà utilisé ailleurs dans le backend (profils, repli du
routeur d'outils) : son quota de tokens par minute est donc partagé. Si le tri
échoue souvent, c'est le premier endroit à regarder (journaux « Médias
progressifs »).

Limite connue : ce chemin ne passe pas par le cache de la recherche complète
(`rechercher_images`). Chaque appel interroge donc toutes les sources
disponibles, y compris celles qui sont payantes (Serper, SerpApi, SearchApi) : la
même demande répétée coûte à chaque fois.

Tests hors réseau : `test_medias_progressifs.py`. Aucun essai avec les vrais
services n'a été fait : les clés des sources et le modèle du tri restent à
vérifier sur le serveur.

## Configuration Railway

Ajouter seulement les clés des sources souhaitées comme variables d'environnement
du service backend. Aucune clé API ni aucun secret ne doit être enregistré dans
le dépôt. Les sources sans clé fonctionnent sans configuration supplémentaire.
