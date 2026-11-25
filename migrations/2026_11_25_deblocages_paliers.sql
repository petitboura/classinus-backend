/*
  Classinus : deblocage de palier par personne (25/11/2026, demande de Bourama).

  Un palier appartient a la PERSONNE, jamais a un agent : Classinus n'a qu'un seul agent (regle visible
  dans le commentaire de la table agents ci-dessous, dans CLAUDE.md et dans docs/chantiers/DEBLOCAGE_PALIERS.md).

  Pour l'instant un administrateur debloque un palier a la main (route admin ou tableau de bord Supabase).
  Plus tard, le webhook de paiement appellera la meme fonction avec source = 'paiement'. Aucun fournisseur
  de paiement n'est branche dans cette etape.

  - Le nom du palier n'est PAS limite par une contrainte : le code le valide contre modeles_llm.palier, pour
    que l'ajout d'un palier ne demande aucune migration.
  - Un deblocage est actif quand revoque_le est vide et que expire_le est vide ou dans le futur. Une
    revocation garde la ligne (historique). Le palier d'une personne est le plus haut de ses deblocages actifs.
  - RLS activee sans aucune regle : seul le backend (cle secrete Supabase) lit et ecrit, comme les tables
    de la liste d'attente. ON DELETE CASCADE vers auth.users pour la personne ; accorde_par passe a NULL.
*/

create table if not exists public.deblocages_paliers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  palier text not null check (palier ~ '^[a-z0-9_]{1,40}$'),
  source text not null default 'manuel' check (source in ('manuel', 'paiement')),
  accorde_par uuid references auth.users(id) on delete set null,
  motif text check (motif is null or char_length(motif) <= 500),
  debut timestamptz not null default now(),
  expire_le timestamptz,
  revoque_le timestamptz,
  created_at timestamptz not null default now(),
  constraint deblocages_paliers_expiration_apres_debut check (expire_le is null or expire_le > debut)
);

create index if not exists deblocages_paliers_actifs_idx
  on public.deblocages_paliers (user_id)
  where revoque_le is null;

alter table public.deblocages_paliers enable row level security;

comment on table public.deblocages_paliers is
  'FR : paliers debloques par personne (manuel aujourd''hui, paiement plus tard). Actif = non revoque et non expire ; le palier d''une personne est le plus haut des actifs. EN: tiers unlocked per person (manual today, payment later). Active = not revoked and not expired; a person''s tier is the highest active one.';

comment on table public.agents is
  'REGLE / RULE : Classinus n''a qu''UN SEUL agent. Ce n''est pas une plateforme multi-agents. Un palier, un abonnement ou un deblocage appartient a la personne (table deblocages_paliers), jamais a un agent. / Classinus has exactly ONE agent. It is not a multi-agent platform. A tier, a subscription or an unlock belongs to the person (table deblocages_paliers), never to an agent.';
