-- Skills autonomes, indépendants des réglages de configuration.
-- Supabase conserve les métadonnées et clés ; les contenus sont dans R2.
create table if not exists public.skills (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users(id) on delete cascade,
    nom text not null check (char_length(nom) between 1 and 120),
    description text not null default '',
    actif boolean not null default true,
    legacy_behavior_id uuid unique,
    legacy_public_id uuid unique,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists skills_owner_updated_idx on public.skills(owner_id, updated_at desc);
alter table public.skills enable row level security;

create table if not exists public.skill_files (
    id uuid primary key default gen_random_uuid(),
    skill_id uuid not null references public.skills(id) on delete cascade,
    chemin text not null check (char_length(chemin) between 1 and 500),
    cle_stockage text not null unique,
    type_mime text not null default 'application/octet-stream',
    taille_octets bigint not null default 0 check (taille_octets >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(skill_id, chemin)
);
create index if not exists skill_files_skill_path_idx on public.skill_files(skill_id, chemin);
alter table public.skill_files enable row level security;

-- Visibilité publique propre à chaque skill (décision du 23/10/2026).
-- prive : visible par son auteur seulement. public : publié. retire : a été
-- publié puis retiré. Les compteurs reprennent ceux du catalogue public actuel
-- (comportements_publics) ; l'API des skills ne modifie jamais ces colonnes.
alter table public.skills add column if not exists visibilite text not null default 'prive';
alter table public.skills add column if not exists retire_le timestamptz;
alter table public.skills add column if not exists activations_count integer not null default 0;
alter table public.skills add column if not exists etoiles_count integer not null default 0;
alter table public.skills add column if not exists cta_count integer not null default 0;
alter table public.skills add column if not exists partages_count integer not null default 0;
do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'skills_visibilite_check') then
        alter table public.skills add constraint skills_visibilite_check check (visibilite in ('prive', 'public', 'retire'));
    end if;
end $$;
create index if not exists skills_visibilite_idx on public.skills(visibilite) where visibilite <> 'prive';
