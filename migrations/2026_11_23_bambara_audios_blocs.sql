/*
  Classinus : page bambara, un vocal par bloc de texte (23/11/2026, demande de Bourama).

  La réponse de Classinus est découpée en blocs (voir core/prompt_voix_bambara.py, note D) et chaque bloc de texte
  est lu à part : son vocal est gardé avec son rang (bloc, 0 pour le premier bloc de texte de la réponse). Un message
  assistant peut donc avoir plusieurs sons « reponse ». La voix de la personne (« question ») garde le rang 0.
  Les sons déjà gardés prennent le rang 0 : ils restent réécoutables, sous le premier bloc.

  Changement sans risque pour l'existant : colonne avec valeur par défaut, puis l'unicité passe de
  (compte, message, sens) à (compte, message, sens, bloc).
*/

alter table public.bambara_audios_messages
  add column if not exists bloc smallint not null default 0 check (bloc >= 0);

drop index if exists public.uq_bambara_audios_messages;
create unique index if not exists uq_bambara_audios_messages_bloc
  on public.bambara_audios_messages (user_id, message_id, sens, bloc);
