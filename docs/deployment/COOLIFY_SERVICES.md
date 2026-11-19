# Classinus service wiring on Coolify

[English version] · [Français](./COOLIFY_SERVICES.fr.md)

This guide documents the connections between the Classinus backend and its three specialized services hosted on Coolify.

## Production addresses

| Service | URL | Endpoint used |
|---|---|---|
| Class-Tech | https://classtech.classinus.com | `/mcp/diagnostic` |
| Video montage | https://montage.classinus.com | `/mcp/video/` |
| Vultr Docker boxes | https://boites.classinus.com | HTTP API `/boites` and `/navigateurs` |

The frontend calls only the Classinus backend. These three services must not be called directly by the browser.

## 1. Backend environment variables

In Coolify, open the Classinus backend service and add:

```env
CLASSTECH_URL_MCP=https://classtech.classinus.com/mcp/diagnostic
MONTAGE_VIDEO_URL=https://montage.classinus.com
BOITES_URL=https://boites.classinus.com
BOITES_TOKEN=<same-long-secret-as-on-boites-service>
```

Never commit secret values to Git or expose them in the frontend.

`EXECUTION_CODE_FOURNISSEUR=docker` is a separate activation switch: `EXECUTION_CODE_FOURNISSEUR=docker` add it only after verifying the service, HTTPS domain, shared token, and end-to-end tests. It then switches code and browser execution from E2B to the Vultr Docker boxes. If the variable is absent or set to `e2b`, E2B remains active.

Class-Tech also has this production domain as its code default. Keep `CLASSTECH_URL_MCP` explicit in Coolify so the production configuration remains visible.

On the main backend, also set `R2_PUBLIC_BASE_URL=https://<public-backend-domain>` if it is not already configured. It must point to the Classinus API domain serving `/fichiers/r2/...`, not to `montage.classinus.com`.

## 2. Class-Tech service

In the Class-Tech Coolify service:

- Public domain: `classtech.classinus.com`.
- Required `MCP_HOTE_PUBLIC`: `classtech.classinus.com` (hostname only, no scheme or path), for the server's DNS-rebinding protection.
- MCP endpoint called by the backend: `https://classtech.classinus.com/mcp/diagnostic`.
- Wake-up health endpoint: `https://classtech.classinus.com/health`.

The backend registry routes diagnostic tools to this server. Tools that require the PC app continue to use the app relay; they do not run on the Class-Tech server.

## 3. Video montage service

In the Coolify montage service:

- Build with the repository-root `Dockerfile.montage`.
- The image already starts `uvicorn api.main_montage:app --host 0.0.0.0 --port ${PORT:-8000}`.
- Expose internal port `8000` in Coolify.
- Public domain: `montage.classinus.com`.
- Required variables: `SUPABASE_URL`, `SUPABASE_SECRET`, `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`.
- `SUPABASE_SECRET` must exactly match the main backend value; it authenticates internal requests to the video gateway.
- All four R2 variables must point to the same account and bucket as the main backend. Also set `R2_PUBLIC_BASE_URL` to the main backend's public base URL (not the montage domain): published video files link to the Classinus backend's `/fichiers/r2/...` route.

The backend builds the full MCP URL by appending `/mcp/video/` and the user and conversation identifiers. Do not add this path to `MONTAGE_VIDEO_URL`.

Health check: `https://montage.classinus.com/sante`.

## 4. Vultr Docker boxes service

In the Coolify Docker Compose resource for `boites_service`:

- Public domain: `boites.classinus.com`.
- Coolify proxy target: API container port `8080`.
- Never publish the boxes' proxy port `3128` to the Internet.
- The Docker socket must remain mounted only in the `boites-service` container.
- Set `BOITES_TOKEN` on the service, then copy the exact same secret to the backend's `BOITES_TOKEN`.

On the backend, `BOITES_URL` is the base URL without a path: `https://boites.classinus.com`. The client appends `/boites`, `/navigateurs`, and the other API paths itself.

Health check: `https://boites.classinus.com/sante`.

The service requires a Bearer token. Generate a long random secret and do not reuse it for another purpose. If the services later share a private Docker network, prefer the internal service address over the public URL after validating DNS resolution and routing from the backend container.

## 5. Activation order

1. Deploy Class-Tech and check `/health`.
2. Deploy the montage service with its dedicated Dockerfile and Supabase/R2 variables, then check `/sante`.
3. Deploy `boites_service`, check `/sante`, and run `boites_service/verifier_serveur.sh` on the Vultr host.
4. Add the backend variables listed above.
5. Redeploy the backend.
6. Check backend logs for MCP connection failures, 401/403 responses, and timeouts.
7. Test a Class-Tech diagnostic, a small video montage, and code execution in a Docker box.
8. Verify that the video result is saved to R2 and accessible from Classinus.

## 6. Rollback

- Video montage: remove `MONTAGE_VIDEO_URL` to use the video server embedded in the backend again.
- Docker: set `EXECUTION_CODE_FOURNISSEUR=e2b` or remove the variable to switch back to E2B. Make sure `E2B_API_KEY` is still configured.
- Class-Tech: set `CLASSTECH_URL_MCP` to another valid MCP URL.

## Security and limitations

HTTPS domains allow the services to connect without depending on a shared Docker container name. For a final setup on the same Coolify host, a shared private network is preferable when the services can genuinely share one. In all cases, retain server-to-server authentication, never expose proxy port `3128`, and never send secrets to the frontend.

The supplied URLs identify the declared production domains. Their live availability, Coolify proxy configuration, and existing service variables still need to be checked in Coolify; this guide does not claim access to those settings.
