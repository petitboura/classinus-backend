# Sandbox service (Vultr hackathon)

[English] · [Français](README.fr.md)

Replaces E2B with Docker boxes on the Vultr server. The Classinus backend calls this service over
HTTP with a token. Only this service touches the Docker socket.

**One box per conversation.** The terminal (code, commands, files) and the Chromium browser (driven by
Playwright, see `pilote.py`) live in the same box. The terminal can start an app (`npm run dev`,
`python3 -m http.server`) and the browser opens it at `http://localhost:PORT`, with nothing leaving the box.

## What is enforced on every box

| Protection | Implementation |
| --- | --- |
| Isolated process | one Docker container per conversation, non-root user (1000), `--cap-drop ALL`, `no-new-privileges`, read-only filesystem |
| Memory and CPU limits | `--memory`, `--memory-swap` (no swap), `--cpus`, `--pids-limit` (tunable: BOITES_MEMOIRE 1536m, BOITES_CPUS, BOITES_PIDS 512) |
| Bounded shared memory and /tmp | `--shm-size` (BOITES_SHM 512m) and a size-capped tmpfs `/tmp` (BOITES_TMP 512m), needed by Chromium |
| Disk space limit | size-capped tmpfs volume (BOITES_DISQUE) |
| Time limit | every command is killed at its deadline (`timeout -k`) |
| No secret inside | the box only receives the proxy variables, no Classinus or Vultr key |
| Network closed by default | internal Docker network (`internal: true`), no route to the Internet |
| Allow-list egress | the only way out is the service proxy, domain by domain, ports 80 and 443, public addresses only (no internal network, no 169.254.x.x) |
| localhost stays in the box | `NO_PROXY=localhost,127.0.0.1,::1`: a local app never goes through the proxy |
| Destruction | `DELETE` removes the container AND its volume; pause stops the container and keeps the files |

Known limit: files live in memory (tmpfs) until the server restarts. A server restart erases workspaces.

## The browser inside the box

`pilote.py` is copied into the image (`/opt/navigateur/pilote.py`). A small local daemon (127.0.0.1:9333)
keeps Chromium open between actions; each action is a `python3 pilote.py <action> <json>` command that
prints one JSON line (page, text, screenshot path).

| Feature | Setting (pilot variable) |
| --- | --- |
| Phone or desktop screen | `device` (iphone, android, desktop, Playwright name) or `width` and `height`, touch and pixel ratio included (PILOTE_APPAREIL_IPHONE, PILOTE_APPAREIL_ANDROID) |
| Screenshot quality | PILOTE_QUALITE (85), PILOTE_ECHELLE (`css` or `device`) |
| Full page | PILOTE_HAUTEUR_MAX (4000 pixels) |
| Scrolling, waiting for an element | PILOTE_ATTENTE_MAX_MS (20000) |
| Console and errors | PILOTE_CONSOLE_MAX (200 lines) |
| Fake network responses | PILOTE_SIMULATIONS_MAX (20), PILOTE_CORPS_MAX (200000) |

## Deploying on the Vultr server (Coolify)

1. New resource, Docker Compose, repository classinus-backend, file `boites_service/docker-compose.yml`.
2. Required variable: `BOITES_TOKEN` (a long random string).
3. Deploy. The `boite-image` service builds the box image (with Chromium, several minutes the first time) and then exits, which is normal.
4. The service is published on server port 8787 (BOITES_PORT_HOTE to change it, 8080 is taken by Coolify).
   Vultr firewall: open 8787 only to the backend addresses, or put the service behind HTTPS (Coolify domain).
   Do not open port 3128 (proxy): it is only meant for the internal network of the boxes.
5. Release order: rebuild the image on the Vultr server FIRST, then deploy the backend.
   A workspace created with the old image has no browser: the tool explains it to the agent, which
   downloads the files, closes the workspace and opens a new one.

## Connecting the Classinus backend

In the backend environment variables (never in code):

    EXECUTION_CODE_FOURNISSEUR=docker
    BOITES_URL=https://<service address>
    BOITES_TOKEN=<the same token>

Without `EXECUTION_CODE_FOURNISSEUR=docker`, the backend keeps using E2B. To roll back: remove the
variable or set it back to `e2b`. The browser only exists in docker mode.

## Tests

    python3 -m unittest test_boites_isolees test_boites_service test_navigateur

The tests run offline (fake Docker). The real container behavior must still be checked on the
server: see `boites_service/verifier_serveur.sh`.
