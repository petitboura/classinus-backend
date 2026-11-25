-- Skills publics sur la table skills (24/11/2026, demande de Bourama).
-- Un skill publié (visibilite = 'public') peut être trouvé et ajouté par l'IA d'un autre
-- utilisateur. Chaque ajout crée une copie indépendante. Quand l'auteur modifie son skill,
-- version_publique augmente : la copie garde son contenu, mais l'IA propose la mise à jour.

alter table public.skills add column if not exists version_publique integer not null default 1;
alter table public.skills add column if not exists publie_le timestamptz;

-- Une ligne par copie ajoutée depuis le catalogue public.
--   copie_id        : le skill créé chez l'utilisateur (supprimé avec lui)
--   skill_source_id : le skill public d'origine (devient null s'il est supprimé, la copie reste)
--   version_copiee  : version_publique de la source au moment de la copie ou de la dernière mise à jour
--   synchronise_le  : instant de la copie ou de la dernière mise à jour (sert à repérer une
--                     modification faite ensuite par l'utilisateur sur sa copie)
create table if not exists public.skill_activations (
    id uuid primary key default gen_random_uuid(),
    skill_source_id uuid references public.skills(id) on delete set null,
    copie_id uuid not null unique references public.skills(id) on delete cascade,
    active_par uuid not null references auth.users(id) on delete cascade,
    version_copiee integer not null default 1,
    synchronise_le timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (skill_source_id, active_par)
);
create index if not exists skill_activations_user_idx on public.skill_activations(active_par);
create index if not exists skill_activations_source_idx on public.skill_activations(skill_source_id);
alter table public.skill_activations enable row level security;
