> [English version](./HIGGSFIELD_TODO.md) · **Version française**

# Higgsfield — état backend branche `feature/higgsfield-catalogue-generation`

Front : voir `HIGGSFIELD_TODO.md` dans `docs/status/` de `classinus-frontend`.

## Déjà en place
- `api/higgsfield.py` branché dans `api/main.py` (router `/api/higgsfield`).
- Schémas `DemandeVideo/Image/Genjutsu/Estimation`, limite `10/min`, `reserver_generation`, `lancer_generation` / `statut_generation` / `annuler_generation` / `estimer_cout`.
- Sauvegarde bibliothèque faite par le serveur (voir « Suivi côté serveur »).

## Reste côté backend (optionnel avant merge)
- Vérifier `HIGGSFIELD_API_KEY` / `HIGGSFIELD_API_BASE_URL` dans l'env Render/Railway (prod + staging).
- Vérifier CORS pour les URLs d'upload R2 renvoyées au frontend.
- Option : webhook Higgsfield si polling jugé fragile (pas prioritaire).

## Suivi côté serveur (6 novembre 2026)

- Chaque lancement (`POST /api/higgsfield/video|image|genjutsu`) est enregistré dans la table `higgsfield_generations` (migration `migrations/2026_11_06_higgsfield_generations.sql` ; RLS active, aucune policy, lignes supprimées avec le compte).
- Une boucle de fond dans `api/main.py` (`_boucle_suivi_higgsfield`, toutes les 5 secondes) exécute `core/higgsfield_suivi.py` : elle interroge Higgsfield, sauvegarde le résultat dans la bibliothèque une seule fois, puis envoie la notification (type `action_ia_terminee`, lien `/higgsfield`) et le push. Cela marche appli fermée, et un redémarrage du serveur ne perd rien car l'état est en base.
- Une génération encore en cours après 2 heures est marquée en échec (`delai_depasse`).
- `GET /api/higgsfield/statut/{id}` lit maintenant la base et vérifie l'appartenance (404 sinon) ; l'ancien paramètre `titre` et la sauvegarde dans cet appel ont été retirés. Nouveau `GET /api/higgsfield/generations` : liste des générations récentes de l'utilisateur. `POST /annuler/{id}` vérifie aussi l'appartenance.
- L'export et la suppression de compte incluent la nouvelle table.
