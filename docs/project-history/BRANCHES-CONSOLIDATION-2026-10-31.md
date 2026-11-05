# Branch consolidation notes: 31 October 2026

[English version] · [Français](BRANCHES-CONSOLIDATION-2026-10-31.fr.md)

Note for the owners of the affected branches. Decision by Bourama, based on Git analysis: ancestry, `git cherry`, and tree diffs against `staging`.

## Branch to use from now on

- **`feat/workspace-code-tools`** (`d1863b6504af671eae2c4f8f269d067106d89a5b`)
  - Already includes `fix/memoire-contenu-objet` as a proven ancestor.
  - Also includes the "Always allow" permissions, complete tool history, and restoration of `api/main.py`.
  - Continue all memory / workspace-code work on this branch, not the older ones.

## Branches deleted on 31 October 2026

| Deleted branch | SHA (can be restored) | Reason |
|---|---|---|
| `fix/memoire-contenu-objet` | `e14088373e97a2b5345f54b5afc309e765cefe4a` | Already included in `feat/workspace-code-tools` |
| `djiguigne-modif-1793394411` | `284bb281175574db8906bf5e7584642da0890dd7` | Broken version: emptied `api/main.py` (-967 lines); fixed in `feat/workspace-code-tools` |
| `djiguigne-modif-1792901222` | `f0226b9bf82181b347036262853aa5d61dc0e4da` | Removed only one SQL migration and diverged by 209 commits |

## Restore a branch if genuinely needed

```bash
git branch <branch-name> <sha-above>
git push origin <branch-name>
```

Unaffected: `main`, `staging`, and all other useful branches and open PRs.
