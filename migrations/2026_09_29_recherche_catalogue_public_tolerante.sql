/* 29/09/2026, demande Bourama : la recherche du catalogue public ne */
/* retrouvait jamais un PDF par son nom ou des mots-cles (171 PDF sur 174 */
/* ne sont pas indexes par le sens, et la recherche par mots-cles exigeait */
/* que TOUS les mots de la question soient dans le document, donc une */
/* phrase naturelle ne trouvait rien). */
/*  */
/* Cette version : un document est trouve s'il contient AU MOINS UN mot */
/* significatif de la question (mots de 3 lettres et plus), classes par */
/* pertinence. Bonus quand tous les mots sont presents, et recherche aussi */
/* directement dans le nom du fichier (sous-chaine). Meme signature et meme */
/* forme de retour que la version precedente : rien a changer cote appelant. */
create or replace function public.recherche_catalogue_public_mots_cles(
  p_question text, match_count integer,
  p_dossier_id uuid default null, p_pays text default null, p_niveau text default null,
  p_categorie text default null, p_classe text default null, p_specialite text default null
)
returns table(fichier_id uuid, nom text, description text, url_publique text, type_mime text, similarite double precision)
language sql
stable
set search_path to 'public', 'extensions'
as $function$
  with mots as (
    /* Mots significatifs de la question : 3 lettres et plus, sans les mots vides (le, sur, moi...) et sans les mots de conversation. */
    select distinct t
    from regexp_split_to_table(lower(coalesce(p_question, '')), '[^[:alnum:]]+') as t
    where length(t) >= 3 and to_tsvector('french', t) <> ''::tsvector
      /* Mots de conversation qui ne decrivent pas le document cherche. */
      and t <> all (array['document','documents','fichier','fichiers','pdf','cherche','chercher','trouve','trouver',
                          'donne','donner','montre','montrer','veux','voudrais','peux','peut','plait','svp','stp','merci'])
  ),
  mw as (
    /* Un mot present dans peu de noms de fichiers pese plus qu'un mot banal (cours, exercices...). */
    select t, 1.0 / (1 + (select count(*) from bibliotheque_publique b2 where b2.statut = 'publie' and b2.nom ilike '%' || t || '%')) as w
    from mots
  ),
  q as (
    select
      plainto_tsquery('french', p_question) as tsq_et,
      to_tsquery('french', nullif((select string_agg(t, ' | ') from mots), '')) as tsq_ou,
      nullif(replace(replace(replace(trim(coalesce(p_question, '')), '\', '\\'), '%', '\%'), '_', '\_'), '') as brut
  )
  select
    bp.id as fichier_id, bp.nom, bp.description, bp.url_publique, bp.type_mime,
    (
      /* Signal dominant : part (ponderee par la rarete) des mots de la question presents dans le NOM du fichier. */
      3 * (select coalesce(sum(mw.w), 0) from mw where bp.nom ilike '%' || mw.t || '%')::double precision
        / greatest((select coalesce(sum(mw.w), 0) from mw), 0.000001)
      /* Signal secondaire, plafonne : pertinence dans la description et le contenu. */
      + 0.5 * least(1.0, greatest(
          2 * ts_rank_cd(to_tsvector('french', coalesce(bp.nom, '') || ' ' || coalesce(bp.description, '')), q.tsq_ou),
          coalesce(max(ts_rank_cd(to_tsvector('french', coalesce(dcp.contenu, '')), q.tsq_ou)), 0),
          ts_rank_cd(to_tsvector('french', coalesce(bp.texte_brut, '')), q.tsq_ou)
        ))
      + case when to_tsvector('french', coalesce(bp.nom, '') || ' ' || coalesce(bp.description, '')) @@ q.tsq_et then 1 else 0 end
      + case when q.brut is not null and bp.nom ilike '%' || q.brut || '%' then 1 else 0 end
    )::double precision as similarite
  from bibliotheque_publique bp
  cross join q
  left join documents_catalogue_public dcp on dcp.fichier_id = bp.id
  where bp.statut = 'publie'
    and (p_dossier_id is null or exists (
      select 1 from fichiers_dossiers_catalogue_public fdcp
      where fdcp.fichier_id = bp.id and fdcp.dossier_id = p_dossier_id
    ))
    and (p_pays is null or exists (select 1 from unnest(bp.pays) v where lower(trim(v)) = lower(trim(p_pays))))
    and (p_niveau is null or exists (select 1 from unnest(bp.niveau) v where lower(trim(v)) = lower(trim(p_niveau))))
    and (p_categorie is null or exists (select 1 from unnest(bp.categorie) v where lower(trim(v)) = lower(trim(p_categorie))))
    and (p_classe is null or exists (select 1 from unnest(bp.classe) v where lower(trim(v)) = lower(trim(p_classe))))
    and (p_specialite is null or exists (select 1 from unnest(bp.specialite) v where lower(trim(v)) = lower(trim(p_specialite))))
    and (
      to_tsvector('french', coalesce(bp.nom, '') || ' ' || coalesce(bp.description, '')) @@ q.tsq_ou
      or to_tsvector('french', coalesce(dcp.contenu, '')) @@ q.tsq_ou
      or to_tsvector('french', coalesce(bp.texte_brut, '')) @@ q.tsq_ou
      or (q.brut is not null and bp.nom ilike '%' || q.brut || '%')
    )
  group by bp.id, bp.nom, bp.description, bp.url_publique, bp.type_mime, bp.texte_brut, q.tsq_et, q.tsq_ou, q.brut
  order by similarite desc
  limit match_count;
$function$;
