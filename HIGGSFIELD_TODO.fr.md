> [English version](./HIGGSFIELD_TODO.md) · **Version française**

# Higgsfield — état backend branche `feature/higgsfield-catalogue-generation`

Front : voir `HIGGSFIELD_TODO.md` à la racine de `classinus-frontend`.

## Déjà en place
- `api/higgsfield.py` branché dans `api/main.py` (router `/api/higgsfield`).
- Schémas `DemandeVideo/Image/Genjutsu/Estimation`, limite `10/min`, `reserver_generation`, `lancer_generation` / `statut_generation` / `annuler_generation` / `estimer_cout`.
- Sauvegarde bibliothèque au `statut` terminé (best-effort).

## Reste côté backend (optionnel avant merge)
- Vérifier `HIGGSFIELD_API_KEY` / `HIGGSFIELD_API_BASE_URL` dans l'env Render/Railway (prod + staging).
- Vérifier CORS pour les URLs d'upload R2 renvoyées au frontend.
- Option : webhook Higgsfield si polling jugé fragile (pas prioritaire).
