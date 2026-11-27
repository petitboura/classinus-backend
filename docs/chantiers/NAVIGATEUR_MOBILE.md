# Browser: one box, phone screens, build then open

[English version] · [Français](NAVIGATEUR_MOBILE.fr.md)

Bourama's decision of 27 November 2026: the `gerer_navigateur` tool must do what Claude does. Open an app on a
phone-sized screen, take good screenshots, build an app and then open it itself.

## Architecture: one box per conversation

- The terminal and Chromium live in the same Docker box (`boites_service/Dockerfile.boite`). The old separate
  browser image, the `/navigateurs` routes and the `BOITES_NAV_*` settings were removed.
- The terminal starts an app (`gerer_execution_code`, `run_background`), the browser opens `http://localhost:PORT`.
  `localhost`, `127.0.0.1` and `::1` are always allowed and never go through the proxy.
- Quota, pause and close are those of the workspace (`_reserver_workspace` and `_travailler_dans_workspace` in
  `core/outils_execution_code.py`). A browser action counts as a short command (`run_command`).
- Account deletion: the browser has no box of its own any more, so `core/purge_compte.py` kills it with the workspace.

## Actions of `gerer_navigateur`

`open`, `click`, `type`, `screenshot`, `submit`, `scroll`, `wait`, `console`, `mock`, `unmock`, `device`,
`demander_acces_reseau`, `close`.

| Need | Parameters |
| --- | --- |
| Phone screen | `device` (iphone, android, desktop or a Playwright name like "iPhone 15") and/or `width` and `height` (200 to 3000). Touch, pixel ratio and user agent come with the device. `click` becomes a tap. |
| Full page | `screenshot` with `full_page=true`, capped at 4000 pixels high (a note says so and suggests scrolling) |
| Scroll | `direction` (down, up, top, bottom), `amount`, or `selector` / `text` to bring an element into view |
| Wait | `selector` or `text`, `timeout_ms` (20 seconds at most) |
| Console | returns and clears console messages, page errors, failed requests and HTTP errors. Shown as untrusted data. |
| Fake network response | `mock` with `url` (pattern like `**/api/notes`), `body`, `status`, `content_type`; `unmock` removes one or all. CORS headers are added so a page on another origin can read it. |

Screenshots are JPEG quality 85 (PILOTE_QUALITE) at CSS scale, so a phone screenshot is 390 pixels wide as the code sees it.

## Rules kept

- `submit` stays sensitive and never "always allow"; `click` refuses final-looking text.
- `close` stops Chromium only. It never uses the workspace `close` action, which destroys the workspace.
- `console`, `mock` and `unmock` send no image.
- A workspace created with the old image has no `/opt/navigateur/pilote.py`: the tool tells the agent to download
  the files, close the workspace and reopen the page.

## Release order

1. Rebuild the box image on the Vultr server (`boites_service/docker-compose.yml`).
2. Deploy the backend.

Not verified here: the behavior on the real Vultr image (Chromium installed by `playwright install`). The pilot was
tested with a real Chrome, the rest with fakes. Run `boites_service/verifier_serveur.sh` on the server.
