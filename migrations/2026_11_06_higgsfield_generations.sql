/*
  Classinus : suivi serveur des generations Higgsfield (page /higgsfield).

  Chaque generation lancee est enregistree ici. Le backend la suit et la
  termine tout seul (sauvegarde en bibliotheque + notification), meme si
  l'application est fermee. L'etat vit en base : un redemarrage du serveur
  ne perd rien.

  RLS activee et AUCUNE policy volontairement : seul le backend (cle secrete
  Supabase) y accede. user_id pointe vers auth.users avec ON DELETE CASCADE,
  les lignes partent avec le compte (voir aussi core/purge_compte.py).
*/
create table if not exists public.higgsfield_generations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  request_id text not null unique,
  titre text not null,
  genre text not null check (genre in ('video', 'image')),
  etat text not null default 'en_cours'
    check (etat in ('en_cours', 'terminee', 'echec', 'bloquee', 'annulee')),
  url text,
  erreur text,
  sauvegardee boolean not null default false,
  notifiee boolean not null default false,
  verifie_a timestamptz,
  cree_a timestamptz not null default now(),
  termine_a timestamptz
);

create index if not exists idx_higgsfield_generations_user
  on public.higgsfield_generations (user_id, cree_a desc);
create index if not exists idx_higgsfield_generations_en_cours
  on public.higgsfield_generations (etat) where etat = 'en_cours';

alter table public.higgsfield_generations enable row level security;
