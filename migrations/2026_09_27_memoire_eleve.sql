-- Chantier "mémoire élève" (27/09/2026, demande Bourama), Lot A.
-- Remplace le principe des tables conversation_summaries /
-- agent_user_profiles (voir core/outils_memoire_profil.py, NON touchées
-- par cette migration, décision de retrait/migration de données pas
-- prise ici) : au lieu d'un unique JSON par élève fusionné au premier
-- niveau seulement (dict.update, donc une clé déjà utilisée écrasait
-- tout son contenu imbriqué), une ligne par (élève, catégorie,
-- sous_categorie). Une écriture ne touche jamais que sa propre ligne.
--
-- Catégories de premier niveau imposées côté application (voir
-- CATEGORIES_MEMOIRE_ELEVE dans core/memoire_eleve.py) : identite,
-- scolarite, apprentissage, preferences. Sous-catégories libres,
-- décidées par le modèle selon chaque élève (notation pointée, ex.
-- "apprentissage" + sous_categorie "maths.derivees").

create table if not exists public.memoire_eleve (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id),
  categorie text not null check (categorie in ('identite', 'scolarite', 'apprentissage', 'preferences')),
  sous_categorie text not null default '',
  contenu jsonb not null default '{}'::jsonb,
  description text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, categorie, sous_categorie)
);
comment on table public.memoire_eleve is
  'Mémoire élève persistante et incrémentale (chantier 27/09/2026). Une ligne = une catégorie/sous-catégorie pour un élève ; jamais de réécriture globale, voir core/memoire_eleve.py::ecrire_categorie.';
comment on column public.memoire_eleve.sous_categorie is
  'Libre, notation pointée si plusieurs niveaux (ex. "maths.derivees"). Chaîne vide (PAS NULL -- deux NULL ne sont jamais égaux pour une contrainte unique en Postgres, ce qui casserait à la fois l''unicité et l''upsert on_conflict) = la ligne représente la catégorie racine elle-même.';
comment on column public.memoire_eleve.description is
  'Résumé en une phrase de ce que contient cette ligne, écrit/mis à jour par le modèle à chaque écriture -- sert à construire le sommaire (memoire_sommaire) sans jamais renvoyer le contenu complet.';
alter table public.memoire_eleve enable row level security;

-- Unicité déjà utile pour trier le sommaire par catégorie, mais un index
-- dédié évite un scan complet dès que la table grossit (beaucoup
-- d'élèves), memoire_sommaire filtrant systématiquement sur user_id.
create index if not exists idx_memoire_eleve_user
  on public.memoire_eleve(user_id, categorie, sous_categorie);

-- Déclaration côté plateforme (voir core/mcp_tools.py,
-- registre_outils_plateforme.disponible) -- sans cette étape les outils
-- existent dans le code mais ne sont jamais proposés au modèle/routeur,
-- même piège documenté dans migrations/2026_09_24_outil_lire_reponses_qcm.sql.
-- Catégorie numérique 1 / nom_serveur 'generation', même valeurs que les
-- autres outils de core/outils_generation_commun.py (mcp_generation).
-- Cache 24h côté serveur : un redémarrage Railway prend le changement en
-- compte tout de suite.
insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('memoire_sommaire', 1, 'generation', true, now()),
  ('memoire_lire', 1, 'generation', true, now()),
  ('memoire_ecrire', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
