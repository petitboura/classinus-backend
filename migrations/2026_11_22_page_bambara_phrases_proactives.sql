/*
  Classinus : page bambara, phrases proactives (22/11/2026, demande de Bourama).

  La page parle d'elle même à six moments, pour que la personne ne reste jamais devant le silence :
  l'arrivée sur la page, une recherche web, une recherche de vidéos, une recherche d'images, la
  création d'une image, et un outil qui prend du temps.

  bambara_phrases_proactives : les phrases, communes à tous les comptes (aucune donnée de compte, donc
    rien à ajouter à la suppression de compte). Le texte bambara est lu par la voix du TTS ; texte_en est
    sa traduction anglaise, pour l'équipe. L'audio est fabriqué par le serveur la première fois puis
    gardé à côté (audio_base64) ; audio_empreinte retient la voix et le texte avec lesquels il a été
    fabriqué : si l'un des deux change, l'audio est refait tout seul.
  bambara_phrases_reglages : une seule ligne, les délais de la phrase « outil lent ».

  Pour ajouter une phrase : une ligne dans bambara_phrases_proactives (moment, texte, texte_en).
  Plusieurs phrases pour un même moment sont des variantes, tirées au hasard.

  Sécurité par ligne activée sans règle : seul le backend (clé secrète) y accède.
*/

create table if not exists public.bambara_phrases_proactives (
  id uuid primary key default gen_random_uuid(),
  moment text not null check (moment in (
    'accueil', 'recherche_web', 'recherche_videos', 'recherche_images', 'creation_image', 'outil_lent'
  )),
  texte text not null check (char_length(btrim(texte)) between 1 and 300),
  texte_en text not null default '' check (char_length(texte_en) <= 600),
  actif boolean not null default true,
  audio_base64 text,
  audio_duree_ms integer check (audio_duree_ms is null or audio_duree_ms >= 0),
  audio_empreinte text,
  cree_a timestamptz not null default now(),
  modifie_a timestamptz not null default now()
);
create index if not exists idx_bambara_phrases_moment on public.bambara_phrases_proactives (moment) where actif;

create table if not exists public.bambara_phrases_reglages (
  id boolean primary key default true check (id),
  /* Secondes d'attente d'un outil avant la première phrase « outil lent ». */
  delai_outil_lent_s integer not null default 6 check (delai_outil_lent_s between 1 and 120),
  /* Secondes entre deux phrases « outil lent » tant que l'outil travaille encore. */
  intervalle_outil_lent_s integer not null default 12 check (intervalle_outil_lent_s between 3 and 300)
);
insert into public.bambara_phrases_reglages (id) values (true) on conflict (id) do nothing;

/* Le texte change : l'audio gardé n'est plus valable, il sera refait. Le serveur compare aussi l'empreinte,
   ce déclencheur couvre en plus une modification faite directement dans Supabase. */
create or replace function public.bambara_phrases_texte_modifie() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.texte is distinct from old.texte then
    new.audio_base64 := null;
    new.audio_duree_ms := null;
    new.audio_empreinte := null;
  end if;
  new.modifie_a := now();
  return new;
end;
$$;

drop trigger if exists trg_bambara_phrases_texte_modifie on public.bambara_phrases_proactives;
create trigger trg_bambara_phrases_texte_modifie
  before update on public.bambara_phrases_proactives
  for each row execute function public.bambara_phrases_texte_modifie();

alter table public.bambara_phrases_proactives enable row level security;
alter table public.bambara_phrases_reglages enable row level security;
