-- Permissions des outils par personne (24/11/2026, demande de Bourama).
--
-- Une ligne = un réglage choisi par la personne, pour un outil précis ou pour une catégorie d'outils
-- d'une application. Trois états : autoriser (jamais de confirmation), demander (confirmation à chaque
-- fois), bloquer (l'outil est refusé et l'IA l'explique).
--
-- cle : nom de l'outil tel que l'IA le voit (ou "outil:action" pour les actions d'un outil à plusieurs
--       actions), OU un réglage de catégorie : "categorie:<groupe>:lecture" ou "categorie:<groupe>:ecriture".
--       <groupe> est le nom de l'application (ex. vercel_mcp, notion) ou, pour un serveur MCP
--       personnalisé, "custommcp_<6 premiers caractères de l'identifiant du serveur>".
--
-- Ordre de priorité à l'exécution : réglage de l'outil, puis de sa catégorie, puis valeur par défaut.
-- Les anciennes sources (autorisations_outils_permanentes et mcp_personnalises.autoriser_non_sensibles)
-- sont reprises ci-dessous puis ne sont plus lues ; on ne les supprime pas, pour pouvoir revenir en arrière.

create table if not exists public.permissions_outils (
  user_id uuid not null references auth.users(id) on delete cascade,
  cle text not null check (char_length(cle) between 1 and 200),
  etat text not null check (etat in ('autoriser', 'demander', 'bloquer')),
  nom_lisible text not null default '' check (char_length(nom_lisible) <= 300),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, cle)
);

-- Même protection que autorisations_outils_permanentes : lecture et écriture réservées au backend.
alter table public.permissions_outils enable row level security;

-- Reprise : les actions déjà "toujours autorisées" passent sur "autoriser".
insert into public.permissions_outils (user_id, cle, etat, nom_lisible, created_at)
select user_id, cle, 'autoriser', left(nom_lisible, 300), created_at
from public.autorisations_outils_permanentes
on conflict (user_id, cle) do nothing;

-- Reprise : "autoriser d'un coup les outils non sensibles" devient le réglage de la catégorie lecture.
insert into public.permissions_outils (user_id, cle, etat, nom_lisible)
select
  user_id,
  'categorie:custommcp_' || substr(replace(id::text, '-', ''), 1, 6) || ':lecture',
  'autoriser',
  left('Outils en lecture seule de ' || nom, 300)
from public.mcp_personnalises
where autoriser_non_sensibles
on conflict (user_id, cle) do nothing;
