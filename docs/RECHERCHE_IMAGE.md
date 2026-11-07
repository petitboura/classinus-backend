# Image search

[English version] · [Français](RECHERCHE_IMAGE.fr.md)

The `rechercher_image` tool (defined in `core/outils_generation_media.py`) finds images that already exist. The search itself lives in `core/recherche_image.py`: a cascade of providers followed by an in-memory cache. It returns a list of `{"titre", "url", "miniature", "credit"}`, and the tool wraps it as `{"images": [...]}`.

Why a cascade: the first version only used Pixabay and Pexels. Those are stock photo libraries, not web search engines, so they never found real places, people, events or textbook diagrams.

## Providers, in default order

| Order | Provider | Key variable | What it brings |
|---|---|---|---|
| 1 | Wikimedia Commons | none | Real photos of places, people, monuments, species |
| 2 | Openverse | none | Openly licensed photos and illustrations from many sources |
| 3 | Serper | `SERPER_API_KEY` | Google Images, the real web |
| 4 | SerpApi | `SERPAPI_API_KEY` | Google Images, backup for Serper |
| 5 | Pixabay | `PIXABAY_API_KEY` | Stock photos, illustrations, vectors |
| 6 | Pexels | `PEXELS_API_KEY` | Stock photos, last resort |

A provider is tried only if the previous one failed or returned nothing (error, quota exceeded, outage, missing key). A provider that needs a key and has none is skipped. The tool never fails because of a provider.

Free allowances at the time of writing (7 November 2026, check each provider before relying on them): Serper gives 2,500 free credits once at sign-up, and they expire after 6 months. SerpApi gives 250 searches per month and 50 per hour on its free plan. Wikimedia Commons and Openverse need no key.

## Settings (all optional)

| Variable | Default | Effect |
|---|---|---|
| `RECHERCHE_IMAGE_ORDRE` | `wikimedia,openverse,serper,serpapi,pixabay,pexels` | Provider order, comma separated. A provider missing from the list is never used. Unknown names are ignored. |
| `RECHERCHE_IMAGE_CACHE_SECONDES` | `259200` (3 days) | Cache lifetime. `0` disables the cache. |
| `RECHERCHE_IMAGE_CACHE_MAX` | `500` | Maximum number of cached searches. The oldest is dropped first. |

Example, to put Google Images first: `RECHERCHE_IMAGE_ORDRE=serper,serpapi,wikimedia,openverse,pixabay,pexels`.

Wikimedia Commons almost always returns something, so with the default order the keyed providers are reached rarely. Change the order if you want Google Images first.

## Cache

A non-empty result is kept in memory for the same normalized query (case and extra spaces ignored) and the same number of images. Errors and empty results are never cached. The cache is per process, which is enough because the backend runs a single `uvicorn` process (see `Procfile`). It is emptied on restart, and `vider_cache_images()` empties it from code.

## Behavior to know

- Only `https` addresses are kept for Wikimedia, Openverse, Serper and SerpApi, because an `http` image is blocked inside an `https` page. For Serper and SerpApi, when the original image is not `https`, the thumbnail (hosted by Google) is used instead.
- The `credit` field names the author or the source site, and is shown in small text in the gallery. Images from the real web are not necessarily free of rights.
- SerpApi is called with its safe search filter on. Wikimedia Commons and Serper are called without any content filter.
- Some websites refuse to let other pages display their images. This has not been measured yet.

## Status

The code and its tests (`test_recherche_image_cascade.py`) were written without network access to the providers. The test responses are fabricated from the providers' documentation. The first real run in production must confirm: the response formats, how many credits one Serper request costs, and whether the images display in the app.

## Setup

1. Create a Serper key (and optionally a SerpApi key).
2. Add `SERPER_API_KEY` (and `SERPAPI_API_KEY`) to the Railway variables of the service.
3. Redeploy, then ask the assistant for a real photo (for example a named monument) and check the gallery and the logs.
