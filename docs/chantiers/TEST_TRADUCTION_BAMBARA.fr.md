# Test des traducteurs bambara (dossier isolé)

[English version](TEST_TRADUCTION_BAMBARA.md) · **Version française**

Dossier temporaire `bambara-traduction/`, isolé du reste du backend (aucun code existant modifié). Même principe que `bambara-ecoute/` et `bambara-bouche/` : un dossier, un déploiement qui sert à la fois la page de test et les traducteurs. À supprimer après les tests.

## Rôle

Un petit serveur avec une seule page de test. On choisit un moteur et un sens de traduction, on écrit une phrase, on lit le résultat. Un locuteur bambara note chaque résultat avec trois boutons (Compris, À moitié, Faux). Le tableau se copie ou se télécharge en CSV, pour comparer avec Kooma. La page et les traducteurs étant servis par la même adresse, il n'y a ni problème de CORS ni de contenu mixte. La page est en français et en anglais.

## Moteurs

| Id | Modèle | Sens | Remarque (lue sur les fiches, pas un avis juridique) |
|---|---|---|---|
| `madlad` | `google/madlad400-3b-mt` | français ou anglais vers bambara, bambara vers français ou anglais | Modèle généraliste. La balise bambara `<2bm>` est à confirmer au premier essai. |
| `nllb_bambara` | `oza75/bm-nllb-1.3B-03` | français ou anglais vers bambara, bambara vers français ou anglais | NLLB adapté au bambara. Dérive de `facebook/nllb-200-distilled-1.3B` : vérifier la licence avant tout usage commercial. Un modèle voisin du même auteur demande d'accepter des conditions, renseigner `HF_TOKEN` si le téléchargement est refusé. |
| `localenlp_eng_bam` | `LocaleNLP/localenlp-eng-bam-0.03` | anglais vers bambara | Modèle Marian, anglais seulement. |
| `localenlp_bam_eng` | `LocaleNLP/localenlp-bam-eng-0.03` | bambara vers anglais | Modèle Marian, anglais seulement. |

Ajouter un moteur revient à ajouter une entrée dans `MOTEURS` de `moteurs.py`.

## Réglages (variables d'environnement)

- `PORT` (8000 par défaut).
- `TEXTE_MAX` (600 par défaut) : longueur maximale du texte en caractères. `TOKENS_MAX` (256 par défaut) : longueur maximale de la traduction.
- `MOTEURS_GARDES` (1 par défaut) : nombre de modèles gardés en mémoire en même temps. 1 est le plus sobre, un autre modèle est déchargé quand on en demande un nouveau.
- `PRECISION` (`bfloat16` par défaut) : `float32` si la mémoire le permet.
- `PRECHARGER_MOTEURS` : identifiants séparés par des virgules à charger au démarrage. Vide par défaut, car avec un seul modèle gardé, tout précharger n'aurait pas de sens.
- `MADLAD_MODELE`, `NLLB_BAMBARA_MODELE`, `LOCALENLP_ENG_BAM_MODELE`, `LOCALENLP_BAM_ENG_MODELE` : pour changer de modèle.
- `TEST_ACCESS_TOKEN` : si défini, `/moteurs` et `/traduire` l'exigent. Ouvrir la page avec `?token=VALEUR`.
- `HF_TOKEN` : seulement si un modèle exige une connexion Hugging Face.
- `HF_HOME` (fixé à `/data/hf` dans le Dockerfile) : dossier où les poids des modèles sont gardés. Monter un volume sur `/data`.

## Déployer sur Coolify

Build pack Dockerfile, dossier de base `/bambara-traduction`, port 8000, domaine commençant par `https://` (pour que Coolify demande un vrai certificat), volume persistant sur `/data`. Chemin de contrôle de santé : `/etat`. Prévoir environ 8 Go de mémoire pour MADLAD en `bfloat16`, sans carte graphique : quelques secondes par phrase, et la première traduction de chaque moteur télécharge le modèle.

## Limites

- Rien n'a été lancé avec les vrais modèles là où ceci a été écrit (pas d'accès à Hugging Face). Les tests utilisent de faux modèles. Vérifier le premier vrai essai dans la page et dans les journaux : un échec de chargement ou de mémoire s'affiche sur la page, avec son détail.
- Aucun comparatif publié n'a été trouvé entre ces moteurs en traduction bambara. Les scores des études sur le bambara sont faibles dans l'ensemble : seul le jugement d'un locuteur sur de vraies phrases permet de choisir.
- Ni compte, ni base de données, rien n'est conservé. Toute personne qui a l'adresse peut utiliser les traducteurs, sauf si `TEST_ACCESS_TOKEN` est défini.

## Lancer les tests

Depuis le dossier : `python3 -m unittest test_app` (aucun modèle téléchargé, PyTorch inutile).
