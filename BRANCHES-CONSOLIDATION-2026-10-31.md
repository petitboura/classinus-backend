# Consolidation des branches en doute — 31/10/2026

Note pour les créateurs des branches concernées (décision Bourama, analyse Git : ancêtres, `git cherry`, diffs d'arbres vs `staging`).

## Branche à utiliser désormais
- **`feat/workspace-code-tools`** (`d1863b6504af671eae2c4f8f269d067106d89a5b`)
  - Contient déjà `fix/memoire-contenu-objet` (ancêtre prouvé).
  - Contient les autorisations « Toujours autoriser », l'historique outils complet et la restauration de `api/main.py`.
  - Continuez tout le travail mémoire / workspace-code sur cette branche, pas sur les anciennes.

## Branches supprimées le 31/10/2026
| Branche supprimée | SHA (restauration possible) | Raison |
|---|---|---|
| `fix/memoire-contenu-objet` | `e14088373e97a2b5345f54b5afc309e765cefe4a` | Déjà incluse dans `feat/workspace-code-tools` |
| `djiguigne-modif-1793394411` | `284bb281175574db8906bf5e7584642da0890dd7` | Version cassée : vidait `api/main.py` (-967 lignes), corrigé dans `feat/workspace-code-tools` |
| `djiguigne-modif-1792901222` | `f0226b9bf82181b347036262853aa5d61dc0e4da` | Supprimait seulement une migration SQL, divergée de 209 commits |

## Restaurer une branche si vraiment nécessaire
```bash
git branch <nom-branche> <sha-ci-dessus>
git push origin <nom-branche>
```

Non touchés : `main`, `staging` et toutes les autres branches utiles / PR ouvertes.
