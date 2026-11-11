# Tests des traducteurs bambara

[English version](TESTS_TRADUCTEURS_BAMBARA.md) · **Version française**

Dossier temporaire `bambara-tests/`, isolé du reste du backend (aucun code existant modifié, aucun déploiement). À supprimer après les tests.

## Rôle
Petit serveur avec une page de test : on choisit un moteur et un sens de traduction, on écrit une phrase, on lit le résultat. Un locuteur bambara note chaque résultat (Compris, À moitié, Faux). Le tableau se copie ou se télécharge en CSV, pour comparer avec Kooma.

## Moteurs
| Moteur | Modèle | Sens |
|---|---|---|
| MADLAD-400 3B | `google/madlad400-3b-mt` | français ou anglais vers bambara, bambara vers français ou anglais |
| LocaleNLP anglais vers bambara | `LocaleNLP/localenlp-eng-bam-0.03` | anglais vers bambara |
| LocaleNLP bambara vers anglais | `LocaleNLP/localenlp-bam-eng-0.03` | bambara vers anglais |

Les identifiants LocaleNLP ont été vérifiés sur Hugging Face. Pour MADLAD, la balise bambara `<2bm>` reste à confirmer au premier test.

## Réglages (variables d'environnement)
- `MAX_LOADED_MODELS` (défaut 1), `MODEL_DTYPE` (défaut bfloat16), `MAX_NEW_TOKENS`, `MAX_INPUT_CHARS`, `PORT`.
- `MADLAD_MODEL`, `LOCALENLP_ENG_BAM_MODEL`, `LOCALENLP_BAM_ENG_MODEL` pour changer de modèle.
- `TEST_ACCESS_TOKEN` : si défini, la traduction exige ce jeton (page ouverte avec `?token=VALEUR`).
- `HF_TOKEN` : seulement si un modèle exige une connexion Hugging Face.

## Mémoire et lenteur
Environ 8 Go de mémoire pour MADLAD en bfloat16, sans carte graphique. Quelques secondes par phrase. La première traduction de chaque moteur télécharge le modèle.

## Lancer
`docker build -t bambara-tests ./bambara-tests`, avec un volume monté sur `/data` pour garder les modèles téléchargés.
