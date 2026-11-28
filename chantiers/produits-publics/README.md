# Chantier: public products (backend)

Branch: `feat/produits-publics` (classinus-backend and classinus-frontend, same name). Requested by Bourama on 28/11/2026.
Full detail, decisions and remaining work: `chantiers/produits-publics/etat.md` in the classinus-frontend repository. Technical reference: [docs/chantiers/produits-publics/README.md](../../docs/chantiers/produits-publics/README.md).

## Decisions (do not reopen without asking him)

1. Any signed-in account publishes, live immediately, no validation first.
2. Images: uploaded by the creator AND captured automatically from the site (both).
3. Entry in the main menu of the app.
4. Report button on each product page, and removal by him (administrator): `POST /api/produits-publics/{id}/retirer-admin` or the report treatment.
5. Public product page rendered on the server so Google reads it.
6. Work on a test branch, not `main`; pushed as is on 28/11.

## Done (28/11/2026)

- Table `produits_publics` and column `signalements_bibliotheque.produit_public_id`, applied on the STAGING database only (project prchrczmcoqngesbzzfi).
- Logic, routes, image upload, automatic capture (desktop then phone, every request checked against internal addresses), report type, administrator removal, account purge, data export, limits in one config file.
- 18 tests passing (`test_produits_publics.py`), i18n tests passing, French and English error messages.
- The report insertion now skips empty fields: the staging table has no `type_emplacement` or `emplacement_id` column, so every report would have failed. To check on production too.

## To do

- Apply the migration on the PRODUCTION database before the move to `main`.
- Test the capture with the real browser on the Coolify server (never tested here: no Chromium in the working environment). Check the browser and its system libraries are in the image, and that the memory limit is enough for two captures at once.
- Check that the R2 image folder is publicly readable and that image addresses work from Google (the images are served by the backend `get_public_url` address).
- Test end to end on staging: publish, upload, capture, report, remove, delete the account (folder in R2 must disappear).
- Possible later: clicks on "Visit", stars, categories (not requested).
- Frontend remaining work: see the frontend `etat.md` (pages, form, English texts, sitemap, Discover pages, docs).
