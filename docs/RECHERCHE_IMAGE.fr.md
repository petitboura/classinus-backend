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
| Pixabay | `PIXABAY_API_KEY` | Banque d'images et illustrations |
| Pexels | `PEXELS_API_KEY` | Banque de photographies |

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

## Configuration Railway

Ajouter seulement les clés des sources souhaitées comme variables d'environnement
du service backend. Aucune clé API ni aucun secret ne doit être enregistré dans
le dépôt. Les sources sans clé fonctionnent sans configuration supplémentaire.
