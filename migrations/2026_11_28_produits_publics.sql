/* Produits publics (28/11/2026, demande de Bourama).
   Un produit (site, appli ou plateforme) est publié par n'importe quel compte, visible tout de suite,
   avec une page publique indexée par Google. Retrait sur signalement ou par un administrateur.
   auteur_id : supprimé avec le compte (ON DELETE CASCADE, voir aussi core/purge_compte.py).
   images    : liste ordonnée d'objets {chemin, alt}, les fichiers sont dans R2 (images-publiques/produits/<compte>/).
   statut    : publie, ou retire (retrait administrateur, la ligne reste avec son motif). */

create table if not exists public.produits_publics (
    id uuid primary key default gen_random_uuid(),
    auteur_id uuid not null references auth.users(id) on delete cascade,
    nom text not null check (char_length(nom) between 2 and 80),
    accroche text not null check (char_length(accroche) between 5 and 140),
    description text not null default '' check (char_length(description) <= 5000),
    type_produit text not null check (type_produit in ('site', 'appli', 'plateforme')),
    url text not null check (char_length(url) <= 500),
    logo_chemin text,
    images jsonb not null default '[]'::jsonb,
    etiquettes text[] not null default '{}',
    statut text not null default 'publie' check (statut in ('publie', 'retire')),
    retire_motif text,
    retire_le timestamptz,
    publie_le timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists produits_publics_liste_idx on public.produits_publics (statut, publie_le desc);
create index if not exists produits_publics_auteur_idx on public.produits_publics (auteur_id);
create index if not exists produits_publics_type_idx on public.produits_publics (type_produit) where statut = 'publie';
create index if not exists produits_publics_etiquettes_idx on public.produits_publics using gin (etiquettes);

alter table public.produits_publics enable row level security;

comment on table public.produits_publics is
    'Produits publics (sites, applis, plateformes) publiés par les comptes. Lecture et écriture uniquement par le backend (rôle de service).';

/* Signalements : une colonne de plus pour viser un produit public. Un produit supprimé emporte ses signalements. */
alter table public.signalements_bibliotheque
    add column if not exists produit_public_id uuid references public.produits_publics(id) on delete cascade;
