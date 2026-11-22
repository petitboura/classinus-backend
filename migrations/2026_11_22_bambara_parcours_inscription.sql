/*
  Classinus : parcours d'inscription vocal de la page bambara (22/11/2026).

  bambara_profils : deux colonnes en plus (genre, presentation). Dans le parcours, la personne dit un seul
    nom à voix haute : il est rangé dans `prenom`, et `nom` peut être vide (la contrainte accepte maintenant 0 à 60 caractères).
  bambara_parcours_textes : les phrases que la voix de Classinus lit à chaque étape du parcours (lues par la
    synthèse vocale). Aucune phrase n'est écrite dans le code : elles sont écrites ici, dans cette table, par l'équipe.
    `texte` est ce que la voix lit. `texte_fr` et `texte_en` disent ce que ça veut dire, pour l'équipe (jamais lus).
    Une phrase absente n'empêche pas le parcours : l'étape se joue alors sans consigne vocale.

  Clés utilisées par le frontend : nom_demande, nom_reecoute, genre_demande, presentation_demande, fin.
  Sécurité par ligne activée sans règle : seul le backend (clé secrète) lit et écrit.
*/

alter table public.bambara_profils add column if not exists genre text;
alter table public.bambara_profils add column if not exists presentation text;

alter table public.bambara_profils drop constraint if exists bambara_profils_genre_check;
alter table public.bambara_profils
  add constraint bambara_profils_genre_check check (genre is null or genre in ('femme', 'homme'));

alter table public.bambara_profils drop constraint if exists bambara_profils_presentation_check;
alter table public.bambara_profils
  add constraint bambara_profils_presentation_check check (presentation is null or char_length(presentation) <= 2000);

alter table public.bambara_profils drop constraint if exists bambara_profils_nom_check;
alter table public.bambara_profils
  add constraint bambara_profils_nom_check check (char_length(btrim(nom)) between 0 and 60);

create table if not exists public.bambara_parcours_textes (
  cle text not null check (char_length(cle) between 1 and 60),
  langue text not null default 'bm' check (char_length(langue) between 2 and 10),
  texte text not null check (char_length(btrim(texte)) between 1 and 600),
  texte_fr text,
  texte_en text,
  actif boolean not null default true,
  modifie_a timestamptz not null default now(),
  primary key (cle, langue)
);
alter table public.bambara_parcours_textes enable row level security;
