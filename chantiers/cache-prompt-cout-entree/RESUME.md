# Coût d'entrée du modèle : cache de prompt

- **Statut** : en cours. Deux correctifs sont prêts sur deux branches du backend, testés en local, pas encore essayés sur le staging, pas fusionnés.
- **Dernière mise à jour** : 2026-11-24
- **Dépôts concernés** : classinus-backend (le frontend n'est pas touché jusqu'ici)
- **Branche(s)** : `fix/cache-mode-cours-partie-variable` (commit c95fc47) et `fix/cache-outils-forces-comme-demander-outils` (commit 311f1e1), toutes deux basées sur `main` au commit 678ee65. Elles se fusionnent ensemble sans conflit.

## Le but, en langage clair
Les fournisseurs de modèles relisent à bas prix (environ un dixième) le début d'une requête qui n'a pas changé depuis l'appel précédent. Bourama trouvait le coût des tokens d'entrée beaucoup trop élevé : il faut donc que le début de chaque requête (liste d'outils, puis prompt système, puis historique) reste identique d'un message à l'autre, pour que le cache serve.

## Ce qui est déjà fait
Vérifié dans le code de `classinus-backend` :
- Claude : 4 points de cache dans `core/adaptateur_claude.py` (dernier outil, système, fin d'historique, dernier message). Durée de 5 minutes par défaut, 1 heure avec `CLAUDE_CACHE_TTL`. Claude n'est pas branché pour l'instant, donc non mesuré.
- GPT et Grok : clé de cache calculée à partir du modèle et du prompt système. Les autres fournisseurs (Vultr, DeepSeek, Gemini...) comptent sur le cache automatique du fournisseur, sans code dédié.
- Le prompt est coupé en une partie stable (avant l'historique) et une partie variable (après), avec le marqueur `MARQUEUR_PARTIE_VARIABLE` dans `core/construction_system_prompt.py`.
- Depuis le 07/11, la liste d'outils ne change plus en cours de tour : `demander_outils` renvoie des fiches dans la conversation et le modèle appelle les outils par `appeler_outil`.
- Chaque appel écrit une ligne `[USAGE]` (taille lue, part lue depuis le cache, empreintes de la tête, des outils et de l'historique), dans `core/usage_llm.py`.

Mesures dans les logs de production (Coolify, `classinus-prod`), modèle glm-5.3 via Vultr uniquement :
- Boucle de 7 étapes (11 appels) : environ 90 % lu depuis le cache.
- Message suivant dans la même conversation : 0 % au premier appel, alors que 65 secondes seulement s'étaient écoulées. La liste d'outils était passée de 10 à 11 outils (`rappeler_resultat_outil` ajouté dès que les résultats d'outils de l'historique dépassent 12 000 caractères). Cause probable, déduite du code, pas prouvée.
- Conversation de 36 appels : environ 90 % lu depuis le cache. Les chutes viennent des compactages d'historique, où le cache retombe autour de 19 000 à 22 000 tokens (la tête et les outils restent lus).
- Une variation temporaire de l'empreinte de la tête du prompt (4120, puis 5b47, puis 4120) : le bloc « MODE COURS » se trouvait dans la partie stable. Piste, pas confirmée.

Correctifs prêts :
1. `fix/cache-mode-cours-partie-variable` : le texte « MODE COURS : ACTIF ou inactif » passe après le marqueur, donc la tête ne change plus quand un code est rattaché ou détaché. Un test vérifie que la tête est identique dans les deux cas (il échoue sans le correctif).
2. `fix/cache-outils-forces-comme-demander-outils` : les outils forcés par le contexte sortent de la liste d'outils. Ils restent envoyés automatiquement, mais comme un outil trouvé par `demander_outils` : fiche à la fin du prompt, appel par `appeler_outil`, exécution via la table de routage. Les outils choisis par Bourama avec le bouton Outils restent dans la liste. Nouvelle fonction `differer_outils_forces` dans `core/routage_outils.py`, 7 tests.

## Ce qui reste à faire
1. Mettre les deux branches sur le staging et rejouer un test sur un modèle Vultr : un message avec une grosse boucle d'outils, puis un message suivant, puis un troisième. Relire les lignes `[USAGE]` (les 500 dernières lignes de Coolify seulement : relire dans les deux minutes). Attendu : une seule chute, puis un retour à un taux élevé.
2. Vérifier qu'un modèle Vultr appelle bien les outils forcés par `appeler_outil` (code actif, média joint, historique allégé...). Risque : un modèle appelle moins bien un outil dont il ne voit pas le schéma dans sa liste.
3. Mesurer la taille des fiches des outils forcés. Elles sont payées au plein tarif à chaque message (partie variable), au lieu d'être relues depuis le cache.
4. Rendre stable la présence de `garder_outils` dans la liste (elle dépend encore de ce que le routeur ou l'utilisateur ajoute).
5. Autres pistes à vérifier : le sommaire de mémoire, le catalogue de skills et la configuration sont dans la partie stable et la changent quand ils changent ; l'allègement de l'historique réécrit d'anciens messages ; la durée de cache de 5 minutes de Claude.
6. Mesurer Claude, GPT, Grok et Gemini quand ils seront branchés.
7. Fusionner dans `main` après la validation de Bourama, puis supprimer les deux branches.

## Décisions prises par Bourama
- Se concentrer sur les modèles Vultr, car Claude n'est pas branché.
- Pour les outils forcés : « les envoyer comme s'ils étaient un outil trouvé par demander_outils », et pas arrêter de les envoyer automatiquement.
- Aucune décision encore sur le stockage des lignes `[USAGE]` dans Supabase (proposé, pas tranché).

## Points ouverts
- Stocker les lignes `[USAGE]` dans Supabase pour garder l'historique des mesures, au lieu de dépendre des logs de Coolify ?
- Faut-il aussi passer les outils de mémoire toujours disponibles par ce chemin ? Pour l'instant ils restent dans la liste, car cette liste est constante.

## Pour l'IA qui reprend ce chantier
- Vérifier d'abord que les deux branches existent toujours et où en est `main` (il bouge vite) ; rebaser si besoin.
- Lancer les tests avec `PYTHONPATH=.:core` : `test_prompt_cache.py`, `test_outils_forces_differes.py`, `test_demander_outils_boucle.py`, `test_consignes_outils.py`, `test_historique_outils_complet.py`. `test_boucle_adaptateurs.py`, `test_completion_outils.py` et `test_outils_memoire_eleve.py` échouaient aussi sur `main` dans l'environnement de la session précédente (non investigué).
- Ne pas affirmer que le cache fonctionne ou non pour un fournisseur sans lignes `[USAGE]` réelles de ce fournisseur.
- Dans `main.py`, la fonction `chat` utilise la liste d'outils pour savoir si les trois outils d'historique sont proposés (`noms_outils_tour`) : les outils différés y sont comptés exprès, ne pas le retirer.
