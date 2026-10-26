/*
  Classinus : compteur quotidien des générations Higgsfield par utilisateur
  (clé API partagée : chaque génération consomme les crédits de Bourama).

  RLS activée et AUCUNE policy volontairement : seul le backend (clé secrète
  Supabase) y accède. user_id pointe vers auth.users avec ON DELETE CASCADE,
  les compteurs partent avec le compte (voir aussi core/purge_compte.py).

  La fonction reserve une génération de façon atomique : elle refuse sans
  rien écrire quand la limite du jour est atteinte, même si deux demandes
  arrivent en même temps. Le jour est compté en UTC.
*/
create table if not exists public.higgsfield_usage (
  user_id uuid not null references auth.users(id) on delete cascade,
  jour date not null default ((now() at time zone 'utc')::date),
  genre text not null check (genre in ('video', 'image')),
  nombre integer not null default 0,
  primary key (user_id, jour, genre)
);

alter table public.higgsfield_usage enable row level security;

create or replace function public.higgsfield_reserver_usage(p_user uuid, p_genre text, p_limite integer)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_nombre integer;
begin
  if p_limite is null or p_limite <= 0 then
    return false;
  end if;
  insert into public.higgsfield_usage (user_id, jour, genre, nombre)
  values (p_user, (now() at time zone 'utc')::date, p_genre, 1)
  on conflict (user_id, jour, genre)
  do update set nombre = public.higgsfield_usage.nombre + 1
  where public.higgsfield_usage.nombre < p_limite
  returning nombre into v_nombre;
  return v_nombre is not null;
end;
$$;

revoke all on function public.higgsfield_reserver_usage(uuid, text, integer) from public, anon, authenticated;
