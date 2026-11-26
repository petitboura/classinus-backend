/*
  Classinus : deblocage d'un modele pour tout le monde ou pour une liste d'adresses (26/11/2026,
  demande de Bourama).

  Un modele debloque ici devient choisissable par la personne concernee MEME s'il est au-dessus de son palier
  ET MEME s'il est marque Bientot (modele ou fournisseur). Deux choses restent exigees : la cle API du
  fournisseur (ou de Vultr / Baseten pour les modeles qui n'y passent que par la) et le fournisseur parmi
  ceux que l'agent unique ouvre (distributeur_debloque). Rien d'autre n'est contourne.

  - email NULL = tout le monde (y compris un visiteur sans compte). Sinon l'adresse du compte, en minuscules
    et sans espaces, comme acces_anticipe_modeles. L'adresse peut etre ajoutee avant que la personne ait un compte.
  - modele_id = modeles_llm.modele_id (verifie par le code contre la configuration, pas par une contrainte,
    pour que l'ajout d'un modele ne demande aucune migration).
  - Actif = revoque_le vide ET (expire_le vide OU dans le futur). Une revocation garde la ligne (historique).
  - Le backend lit la table avec la configuration des modeles (cache d'environ 1 minute) : un deblocage
    ou une revocation prend effet en moins d'une minute.
  - RLS activee sans aucune regle : seul le backend (cle secrete Supabase) lit et ecrit. La table porte des
    adresses e-mail : elle est purgee a la suppression du compte et incluse dans l'export (par adresse).
*/

create table if not exists public.deblocages_modeles (
  id uuid primary key default gen_random_uuid(),
  modele_id text not null check (char_length(modele_id) between 1 and 200),
  email text check (email is null or email = lower(btrim(email))),
  accorde_par uuid references auth.users(id) on delete set null,
  motif text check (motif is null or char_length(motif) <= 500),
  debut timestamptz not null default now(),
  expire_le timestamptz,
  revoque_le timestamptz,
  created_at timestamptz not null default now(),
  constraint deblocages_modeles_expiration_apres_debut check (expire_le is null or expire_le > debut)
);

create index if not exists deblocages_modeles_actifs_idx
  on public.deblocages_modeles (modele_id)
  where revoque_le is null;

create index if not exists deblocages_modeles_email_idx
  on public.deblocages_modeles (email)
  where email is not null;

alter table public.deblocages_modeles enable row level security;

comment on table public.deblocages_modeles is
  'FR : modeles debloques pour tout le monde (email vide) ou pour une adresse, malgre le palier et le Bientot ; la cle API reste exigee. Actif = non revoque et non expire. EN: models unlocked for everyone (empty email) or for one address, despite the plan and Coming soon; the API key is still required. Active = not revoked and not expired.';
