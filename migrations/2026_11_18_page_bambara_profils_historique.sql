/*
  Classinus : page bambara, profils, historique et éléments gardés (18/11/2026).

  bambara_profils : les personnes qui se servent d'un même compte (nom et prénom, rien d'autre).
  bambara_conversations : une ligne par conversation, avec son premier message (texte écrit, ou
    seulement un indicateur « vocal » quand la personne a parlé).
  bambara_audios : le premier vocal d'une conversation, gardé à part pour que la liste de
    l'historique reste légère (WAV encodé en base64, durée et hauteurs des barres de la bulle).
  bambara_gardes : les vidéos et les images gardées par une personne.

  Toutes les tables suivent le compte avec ON DELETE CASCADE (suppression du compte) et ont la
  sécurité par ligne activée sans règle : seul le backend (clé secrète) y accède.
*/

create table if not exists public.bambara_profils (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  nom text not null check (char_length(btrim(nom)) between 1 and 60),
  prenom text not null check (char_length(btrim(prenom)) between 1 and 60),
  cree_a timestamptz not null default now()
);
create index if not exists idx_bambara_profils_user on public.bambara_profils (user_id, cree_a);

create table if not exists public.bambara_conversations (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  profil_id uuid references public.bambara_profils(id) on delete cascade,
  texte text,
  a_audio boolean not null default false,
  cree_a timestamptz not null default now()
);
create index if not exists idx_bambara_conversations_liste
  on public.bambara_conversations (user_id, profil_id, cree_a desc);

create table if not exists public.bambara_audios (
  conversation_id uuid primary key references public.bambara_conversations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  audio_base64 text not null,
  duree_ms integer not null check (duree_ms >= 0),
  pics jsonb not null default '[]'::jsonb,
  cree_a timestamptz not null default now()
);
create index if not exists idx_bambara_audios_user on public.bambara_audios (user_id);

create table if not exists public.bambara_gardes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  profil_id uuid references public.bambara_profils(id) on delete cascade,
  genre text not null check (genre in ('video', 'image')),
  url text not null check (char_length(url) between 1 and 2000),
  titre text not null default '' check (char_length(titre) <= 300),
  miniature text check (miniature is null or char_length(miniature) <= 2000),
  id_video text check (id_video is null or char_length(id_video) <= 64),
  cree_a timestamptz not null default now()
);
/* Une même vidéo ou image n'est gardée qu'une fois par personne (sans profil : un « profil vide » commun). */
create unique index if not exists uq_bambara_gardes_unique
  on public.bambara_gardes (user_id, coalesce(profil_id, '00000000-0000-0000-0000-000000000000'::uuid), url);
create index if not exists idx_bambara_gardes_liste on public.bambara_gardes (user_id, profil_id, genre, cree_a desc);

alter table public.bambara_profils enable row level security;
alter table public.bambara_conversations enable row level security;
alter table public.bambara_audios enable row level security;
alter table public.bambara_gardes enable row level security;
