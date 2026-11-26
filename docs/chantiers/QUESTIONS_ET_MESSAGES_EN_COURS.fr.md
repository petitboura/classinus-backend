# Messages et questions pendant que Classinus travaille (chat)

[English version](QUESTIONS_ET_MESSAGES_EN_COURS.md) · **Version française**

Ajouté le 25 novembre 2026 à la demande de Bourama. Le chat normal fait maintenant ce que le canal en direct savait déjà faire : l'utilisateur peut écrire pendant que Classinus travaille, et Classinus peut poser une question sans arrêter son tour.

## Ce que ça fait

1. **Un message envoyé pendant un tour ne l'arrête pas.** Il va dans la même file d'attente, par utilisateur, que le canal en direct (`core/canal_agent_applicatif.py`, `deposer_message_etudiant`). La boucle d'agent (`core/boucle_agent.py`) relit la file à chaque aller-retour avec le modèle. S'il n'y a pas de tour en cours, ou si le message est trop long pour la file (plus de 2000 caractères), la route répond `pris_en_compte: false` et la page l'envoie comme un message normal : rien n'est coupé ni perdu.
2. **Un seul outil de question, `poser_question`, avec un réglage `bloquante`.**
   - Non bloquante (par défaut) : l'outil répond tout de suite, la tâche continue, et la réponse arrive plus tard par la file, comme un message.
   - Bloquante : la tâche est vraiment coincée, donc l'appel attend la réponse dans le même tour. Classinus ne s'arrête pas pour écrire une question que l'utilisateur lirait ensuite.
   - Pas de réponse dans le délai : l'outil répond « pas de réponse ». Classinus termine son tour normalement, explique qu'il ne peut pas continuer, et repose la même question dans un bloc `question` de son message.
3. **« Autre » par défaut sur les choix, et un champ libre sur les questions à plusieurs champs.** Dans la consigne des questions (`core/profils_agents.py`) et, pour l'outil, dans `core/questions_utilisateur.py` (`autre` vaut vrai sauf si le modèle le met à faux). Une question à plusieurs champs se termine par un champ texte libre « Un avis, une précision ? » dans la langue de l'utilisateur.

## Comment marche une question bloquante

- `core/execution_outils.py` émet l'événement de flux `question_en_direct` juste après l'événement `statut` et AVANT que l'outil ne commence à attendre : la carte s'affiche tout de suite. L'identifiant de la question est celui de l'appel d'outil, que la page connaît déjà.
- Le même fichier donne cet identifiant à l'outil (`id_question`), en écrasant tout ce que le modèle aurait envoyé.
- L'outil (`core/outils_question.py`) attend une Future enregistrée dans `core/canal_agent_applicatif.py` (`attendre_reponse_question`). Ce sont les mêmes attentes que pour les clics : le bouton Arrêter libère donc une question en attente sans code de plus (`annuler_attentes`).
- La page envoie la réponse à `POST /api/chat/question-reponse`. La route vérifie que la question appartient au compte connecté (`repondre_question`) avant de résoudre l'attente.
- Si l'attente est déjà finie (question non bloquante, ou délai dépassé), la même route met la réponse dans la file sous la forme « Réponse à ta question ... », ou renvoie `pris_en_compte: false` pour que la page l'envoie comme un message normal.

## Routes (`api/chat_en_cours.py`)

| Route | Corps | Réponse |
| --- | --- | --- |
| `POST /api/chat/message-en-cours` | `texte` | `pris_en_compte` (vrai : mis en file, faux : l'envoyer comme un message normal) |
| `POST /api/chat/question-reponse` | `id_question`, `reponse`, `question` (facultatif) | `statut` : `recue` (attente bloquante résolue), `en_file` (mise en file), `a_renvoyer` (l'envoyer comme un message normal), plus `pris_en_compte` |

Un texte vide renvoie l'erreur typée `REPONSE_CHAT_VIDE` (message français et anglais dans `core/erreurs.py`).

## Le délai d'attente

- Stocké dans la table Supabase `parametres_outils`, clé `delai_reponse_question_secondes`, en secondes. Valeur de départ : 600 (10 minutes). Valeur de repli dans `core/mcp_tools.py` si la ligne manque.
- Le code le garde entre 30 secondes et 840 secondes. La limite Railway de 15 minutes (900 s) par requête est le chiffre qu'on nous a donné mais elle n'a PAS été confirmée dans la documentation de Railway : le maximum reste en dessous par prudence. Il se change avec la variable d'environnement `QUESTION_DELAI_MAX_SECONDES` si Railway change sa limite.
- Le délai général des outils (60 s, `core/mcp_tools.py::appeler_outil`) ne s'applique PAS à une question bloquante : son délai est le réglage plus une marge de 20 secondes, pour que l'outil rende lui-même « pas de réponse » avant que l'appel ne soit coupé. Une question non bloquante garde le délai général.
- Le flux du chat reste ouvert pendant l'attente grâce au signe de vie que le flux envoie déjà, et les tours des comptes connectés sont détachés (`core/tours_detaches.py`) : si la connexion tombe, la page se rattache au tour.
- Pour changer le délai sans toucher au code : `update parametres_outils set valeur = 300, updated_at = now() where cle = 'delai_reponse_question_secondes';` Le réglage est mis en cache 24 heures : redémarrer le service Railway pour l'appliquer tout de suite.

## Disponibilité

L'outil est forcé parmi les outils du modèle pour tout compte connecté (`core/main.py`, `outils_forces_contexte`), sauf sur les messages automatiques, où personne n'est là pour répondre. Il lui faut aussi sa ligne dans `registre_outils_plateforme` (migration ci-dessous). Aucune donnée n'est liée à un compte : rien n'est ajouté à la purge de compte ni à l'export des données.

## À déployer

1. Déployer le code du backend.
2. Appliquer `migrations/2026_11_25_questions_en_cours_chat.sql` sur la base de staging d'abord, puis en production.
3. Redémarrer le service Railway (le catalogue des outils et les réglages sont mis en cache 24 heures).

## Fichiers

- Nouveaux : `core/questions_utilisateur.py`, `core/outils_question.py`, `api/chat_en_cours.py`, `migrations/2026_11_25_questions_en_cours_chat.sql`, `tests/verifier_question_bloquante.py`, `tests/verifier_delai_question_outil.py`.
- Modifiés : `core/canal_agent_applicatif.py`, `core/execution_outils.py`, `core/mcp_tools.py`, `core/main.py`, `core/boucle_agent.py` (le message mis en file ne cite plus `dire_a_l_etudiant` quand cet outil n'est pas disponible), `core/profils_agents.py`, `core/registre_outils.py`, `core/libelles_outils_anglais.py`, `core/erreurs.py`, `core/serveur_mcp_generation.py`, `api/main.py`, `tests/verifier_delai_outils.py` (réparé : il ne tournait plus).

## Vérifications

`python3 tests/verifier_question_bloquante.py` et `python3 tests/verifier_delai_question_outil.py` couvrent : la lecture et les valeurs par défaut de la question, l'événement de carte, l'attente depuis le fil et la boucle propres à l'outil, la réponse d'un autre compte refusée, le délai dépassé, le bouton Arrêter, le réglage du délai et ses bornes, et le fait qu'une question bloquante n'est pas coupée par le délai général de 60 secondes.

## Rouvrir la page

Rouvrir la page pendant une attente bloquante redessine la carte : `core/persistance_tours.py` garde toutes les lignes du flux sans filtrer par type, donc `question_en_direct` est rejoué, et le frontend (`ChatIA.tsx`, `traiterEvenement`) construit la carte à partir de lui. La moitié frontend est décrite dans `classinus-frontend/docs/chantiers/messages-et-questions-en-cours.fr.md`.
