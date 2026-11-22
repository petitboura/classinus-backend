/*
  Classinus : page bambara, tous les messages audio d'une conversation (22/11/2026, demande de Bourama).

  Avant, seul le premier vocal de la personne était gardé (bambara_audios). Maintenant chaque vocal de la
  personne et chaque voix de Classinus est gardé, rattaché au message écrit correspondant de
  historique_conversations (message_id) : en rouvrant une conversation de l'historique, on réécoute tout.
  sens : « question » (la voix de la personne, rattachée à son message user) ou « reponse » (la voix de
  Classinus, rattachée à son message assistant). WAV encodé en base64, durée et hauteurs des barres.

  La table suit le compte avec ON DELETE CASCADE et a la sécurité par ligne activée sans règle : seul le
  backend (clé secrète) y accède.
*/

create table if not exists public.bambara_audios_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid not null,
  message_id bigint not null,
  sens text not null check (sens in ('question', 'reponse')),
  audio_base64 text not null,
  duree_ms integer not null check (duree_ms >= 0),
  pics jsonb not null default '[]'::jsonb,
  cree_a timestamptz not null default now()
);
create unique index if not exists uq_bambara_audios_messages
  on public.bambara_audios_messages (user_id, message_id, sens);
create index if not exists idx_bambara_audios_messages_conversation
  on public.bambara_audios_messages (user_id, conversation_id, cree_a);

alter table public.bambara_audios_messages enable row level security;
