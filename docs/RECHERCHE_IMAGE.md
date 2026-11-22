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

## Display: the AI chooses

Since November 8, 2026, nothing is shown automatically after an image search (or a video search). The tool returns its results under the key `images_trouvees` (and `videos_trouvees` for videos), which the automatic display does not recognise. The AI reads the titles, keeps only what matches the request, and writes each image as markdown `![title](url)` at the point of its message where it talks about it. If no result fits, it places none and says so.

Do not rename these keys to `images` or `videos`: those names trigger the automatic display of every result, which other tools rely on (browser captures, Higgsfield). Test: `tests/verifier_recherche_media_choix_ia.py`.

## Progressive display (bambara page)

Added on 22 November 2026, at Bourama's request. It only applies to the bambara
page (`client` = `page_bambara`): every other client is unchanged.

The user of that page cannot read, they understand what they see. Before,
`rechercher_image` waited for the slowest source, then the main model sorted and
wrote its images: nothing showed up before the end. Now:

1. Each source answers on its own. As soon as one has answered, its results,
   without the duplicates already seen (same domain and path), go to a small fast
   LLM that picks, by number, the ones that really match the request.
2. The kept images go straight to the screen in an SSE event `bloc_media`, while
   the other sources are still working:
   `{"type": "bloc_media", "id_appel": "...", "genre": "images", "source": "Openverse", "images": [...]}`.
3. At the end, the main model receives a short summary: how many images are
   already on screen, their titles, and the instruction not to copy their
   addresses. If sorting a batch failed (timeout, unreadable answer), that batch
   is not displayed: it is given to the main model under `images_trouvees`, as
   before, so it can choose by itself.

`page` and `nombre` keep their meaning: `page` goes to the sources (the model calls
the tool again with `page=2` to see more, and the summary suggests
`page_suivante_suggeree`), `nombre` caps what is displayed and never goes above
the `MEDIAS_PROGRESSIFS_MAX_IMAGES` setting. An invalid value falls back to the
default.

The small LLM points at results by number and the code writes the addresses: an
LLM that copies a long address sometimes gets one character wrong, and a broken
image cannot be noticed on a page without text.

Why a channel: tools go through a network MCP client, so a tool thread cannot
write directly into the reply stream. `core/medias_progressifs.py` provides a
queue (`CanalMedias`) that the loop in `core/execution_outils.py` empties every
0.05 s while it waits for the tools, to send each block before the tool result.
The bambara page marks the routes of `rechercher_image` and `rechercher_video` in
`core/outils_page_bambara.py` (key `medias_progressifs`).

Settings, all optional (backend environment variables): `MEDIAS_PROGRESSIFS_MODELE`
(Groq model used for sorting, default `openai/gpt-oss-20b`),
`MEDIAS_PROGRESSIFS_DELAI_LLM_SECONDES` (8), `MEDIAS_PROGRESSIFS_LLM_PARALLELES`
(6), `MEDIAS_PROGRESSIFS_PAR_SOURCE` (12), `MEDIAS_PROGRESSIFS_MAX_IMAGES` (60),
`MEDIAS_PROGRESSIFS_MAX_VIDEOS` (30), `MEDIAS_PROGRESSIFS_DELAI_SECONDES` (25).

The default model is already used elsewhere in the backend (profiles, tool router
fallback), so its per-minute token quota is shared. If sorting often fails, look
there first (logs "Médias progressifs").

Known limit: this path does not use the cache of the full search
(`rechercher_images`). Every call therefore queries all available sources,
including the paid ones (Serper, SerpApi, SearchApi): the same request repeated
costs every time.

Offline tests: `test_medias_progressifs.py`. Nothing was tried against the real
services: the source keys and the sorting model still need checking on the server.

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
