# Messages and questions while Classinus works (chat)

**English version** · [Version française](QUESTIONS_ET_MESSAGES_EN_COURS.fr.md)

Added on 25 November 2026 at Bourama's request. The normal chat now does what the live channel already did: the user can write while Classinus is working, and Classinus can ask a question without stopping its turn.

## What it does

1. **A message sent during a turn does not stop it.** It goes into the same per-user queue as the live channel (`core/canal_agent_applicatif.py`, `deposer_message_etudiant`). The agent loop (`core/boucle_agent.py`) reads the queue at every round trip with the model. If no turn is running, or the message is too long for the queue (more than 2000 characters), the route answers `pris_en_compte: false` and the page sends it as a normal message, so nothing is cut or lost.
2. **One question tool, `poser_question`, with a `bloquante` setting.**
   - Not blocking (default): the tool answers at once, the task goes on, and the answer comes later through the queue as a message.
   - Blocking: the task is really stuck, so the call waits for the answer inside the same turn. Classinus does not stop to write a question the user would read afterwards.
   - No answer within the delay: the tool answers "no answer". Classinus ends its turn normally, explains that it cannot continue, and asks the same question again in a `question` block of its message.
3. **"Other" by default on choices, and a free field on multi-field questions.** In the question instruction (`core/profils_agents.py`) and, for the tool, in `core/questions_utilisateur.py` (`autre` is true unless the model sets it to false). A multi-field question ends with a free text field "A view, a detail?" in the user's language.

## How a blocking question works

- `core/execution_outils.py` emits the stream event `question_en_direct` right after the `statut` event and BEFORE the tool starts waiting, so the card shows at once. The question id is the tool call id, which the page already knows.
- The same file gives the tool that id (`id_question`), overwriting anything the model sent.
- The tool (`core/outils_question.py`) waits on a Future registered in `core/canal_agent_applicatif.py` (`attendre_reponse_question`). These are the same waits as for clicks, so the Stop button frees a waiting question with no extra code (`annuler_attentes`).
- The page sends the answer to `POST /api/chat/question-reponse`. The route checks the question belongs to the signed-in account (`repondre_question`) before resolving the wait.
- If the wait is already over (not blocking, or delay passed), the same route puts the answer in the queue as "Answer to your question ...", or returns `pris_en_compte: false` so the page sends it as a normal message.

## Routes (`api/chat_en_cours.py`)

| Route | Body | Answer |
| --- | --- | --- |
| `POST /api/chat/message-en-cours` | `texte` | `pris_en_compte` (true: queued, false: send it as a normal message) |
| `POST /api/chat/question-reponse` | `id_question`, `reponse`, `question` (optional) | `statut`: `recue` (blocking wait resolved), `en_file` (queued), `a_renvoyer` (send it as a normal message), plus `pris_en_compte` |

An empty text returns the typed error `REPONSE_CHAT_VIDE` (French and English message in `core/erreurs.py`).

## The waiting delay

- Stored in the Supabase table `parametres_outils`, key `delai_reponse_question_secondes`, in seconds. Starting value: 600 (10 minutes). Fallback in `core/mcp_tools.py` if the row is missing.
- The code keeps it between 30 seconds and 840 seconds. Railway cuts an HTTP request after 15 minutes (900 s) of total duration, so the maximum stays under it. It can be changed with the environment variable `QUESTION_DELAI_MAX_SECONDES` if Railway changes its limit.
- The general tool delay (60 s, `core/mcp_tools.py::appeler_outil`) does NOT apply to a blocking question: its delay is the setting plus a 20 second margin, so the tool itself answers "no answer" before the call is cut. A non-blocking question keeps the general delay.
- The chat stream stays open during the wait thanks to the keep-alive signal the stream already sends, and turns of signed-in accounts are detached (`core/tours_detaches.py`): if the connection drops, the page reattaches to the turn.
- To change the delay without touching code: `update parametres_outils set valeur = 300, updated_at = now() where cle = 'delai_reponse_question_secondes';` The setting is cached for 24 hours: restart the Railway service to apply it at once.

## Availability

The tool is forced into the model's tools for every signed-in account (`core/main.py`, `outils_forces_contexte`), except on automatic messages, where nobody is there to answer. It also needs its row in `registre_outils_plateforme` (migration below). No data is linked to an account, so nothing is added to the account purge or the data export.

## To deploy

1. Deploy the backend code.
2. Apply `migrations/2026_11_25_questions_en_cours_chat.sql` on the staging database first, then production.
3. Restart the Railway service (the tool catalogue and the settings are cached for 24 hours).

## Files

- New: `core/questions_utilisateur.py`, `core/outils_question.py`, `api/chat_en_cours.py`, `migrations/2026_11_25_questions_en_cours_chat.sql`, `tests/verifier_question_bloquante.py`, `tests/verifier_delai_question_outil.py`.
- Changed: `core/canal_agent_applicatif.py`, `core/execution_outils.py`, `core/mcp_tools.py`, `core/main.py`, `core/boucle_agent.py` (the queued message no longer mentions `dire_a_l_etudiant` when that tool is not available), `core/profils_agents.py`, `core/registre_outils.py`, `core/libelles_outils_anglais.py`, `core/erreurs.py`, `core/serveur_mcp_generation.py`, `api/main.py`, `tests/verifier_delai_outils.py` (repaired: it no longer ran).

## Checks

`python3 tests/verifier_question_bloquante.py` and `python3 tests/verifier_delai_question_outil.py` cover: reading and defaults of the question, the card event, the wait from the tool's own thread and loop, an answer from another account refused, delay passed, the Stop button, the delay setting and its limits, and the fact that a blocking question is not cut by the 60 second general delay.

## Open point

Opening the page again during a blocking wait must redraw the card. The question events are part of the stream replayed when the page reattaches to a turn, but the front end must be checked on this case once its part is done.
