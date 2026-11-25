# Tool line and AI notes (the `commenter` tool)

[English version] · [Français](LIGNE_OUTILS_COMMENTAIRE.fr.md)

Request of 25 November 2026. In the chat, the tool activity is one collapsed line where each new line replaces the previous one, like a wheel turning upward. The AI can also slip a short note to the user between its tool calls, shown as its own line with a dot icon. The display part lives in the frontend repository (`OutilResultatBulle.tsx`). This page describes the backend part.

## The `commenter` internal tool

- Defined in `core/routage_outils.py` (`_outil_commenter`, `_separer_appels_commenter`). Like `garder_outils`, it is never routed to `table_routage`, never counted among the tool calls of the turn and never part of the repetition detection.
- Added in `core/main.py`, after `demander_outils`, whenever tools are offered. Not offered to the Bambara voice client, which has no timeline on screen.
- The definition is fixed, so the prompt cache is not broken. It is written in English on purpose: the note must be written in the language of the user's most recent message.
- One parameter, `texte`. The text is cleaned by `nettoyer_commentaire` in `core/libelles_activite_ia.py` (one line, no tags or brackets, no double hyphens, 240 characters at most). An unusable note is not shown and the model is told it was ignored.
- Cap: `MAX_COMMENTAIRES_PAR_TOUR` notes per turn (`core/boucle_agent.py`). Beyond it, the model is told to stop writing notes.

## Events and persistence

- The loop sends one `commentaire` event per note (`texte`, `id_appel`), with no `statut` and no `outil_resultat`. The model receives a short synthetic reply and keeps working.
- The note is not translated by the chat server: the AI already writes it in the right language.
- `_capturer_reponse` stores it in `meta["segments"]` as `{"type": "commentaire", "texte": ...}`, in order, so the line survives reopening a conversation. It is never stored in `meta["outils"]`, since there is nothing to replay to the model.

## Tests

`test_commenter_outil.py` plays the real loop with a fake provider: event, model reply, cap, persistence, cleaning and fixed definition.
