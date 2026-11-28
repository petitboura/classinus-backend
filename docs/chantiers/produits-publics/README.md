# Public products (backend)

**English version** · [Version française](README.fr.md)

Chantier of 28 November 2026, requested by Bourama: a new "Products" section where any signed-in person publishes their product (a website, an app or a platform). Each product has a public page indexed by Google, with images, name, tagline, description, type, tags and a link.

## Decisions

- **Who publishes.** Any signed-in account, live immediately, no validation first.
- **Moderation.** Removal after a report (`signalements_bibliotheque`, type `produit_public`) or directly by an administrator (`POST /api/produits-publics/{id}/retirer-admin`). A removed product keeps its row (`statut = 'retire'`, reason, date) and disappears from every public route (404).
- **Images.** Uploaded by the creator and/or captured automatically from the site (desktop then phone). Stored in R2, bucket `images-publiques`, folder `produits/<account id>/`. Every image is re-encoded (JPEG, or PNG when transparent) and reduced to 1800 px wide; a logo is cropped to a 512 px square.
- **Author name.** Shown only when the author has a public profile, otherwise the page says nothing about who published it.

## Limits (all in `core/config_produits_publics.py`, overridable by environment variable)

20 published products per account, 8 images per product, 8 MB per uploaded image, 5 tags, 12 captures per hour per account, 2 captures at once on the server.

## Safety of the capture

The headless browser sends every request (page, redirects, scripts, images) through `valider_url_externe`: an address that points to the internal network is cut. Service workers and WebSockets are blocked and downloads are refused.

## Routes

`GET /api/produits-publics` (search `q`, `type_produit`, `etiquette`, paging `decalage` and `limite`), `GET /api/produits-publics/{id}`, `GET /api/produits-publics/mes-produits`, `POST` (publish), `PUT /{id}`, `DELETE /{id}`, `POST /images` (multipart, `logo` flag), `POST /capture`. List and detail need no account.

## Code map

- `core/produits_publics.py`: validation and all the logic.
- `core/images_produits_publics.py`: upload, capture, purge of a folder.
- `core/config_produits_publics.py`: every limit.
- `api/produits_publics.py`: routes. `api/signalements.py`: new report type.
- `migrations/2026_11_28_produits_publics.sql`: table `produits_publics` and column `produit_public_id` on the reports.
- Tests: `test_produits_publics.py`.

## Account deletion and export

`produits_publics` is purged with the account (`core/purge_compte.py`, which also deletes the image folder in R2) and exported (`produits_publics` in `api/profiles.py`). The foreign key cascades to `auth.users`.

## Status

Table applied on the staging database. Production database: not yet, to apply when the work moves to `main`.
