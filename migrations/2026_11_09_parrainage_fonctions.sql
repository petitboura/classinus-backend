/*
  Classinus : parrainage, fonctions atomiques (étape 3).

  Toutes les fonctions sont réservées au backend (clé secrète Supabase) : aucun utilisateur ne
  peut les appeler lui-même.

  parrainage_generer_code : fabrique un code court et unique (longueur réglable en base).
  parrainage_profil_assurer : crée le profil de parrainage d'un compte (code + email normalisé)
    s'il n'existe pas encore, et renvoie son code.
  parrainage_enregistrer : appelée par le backend quand un compte arrive avec un lien de parrainage.
    - enregistre le parrain (une seule fois par filleul),
    - refuse si c'est un email jetable ou une variante d'un email déjà connu,
    - laisse en attente tant que l'email n'est pas confirmé (réglage Supabase « Confirm email »),
    - une fois l'email confirmé, valide et donne les crédits au parrain, une seule fois.
    Rappeler la fonction pour un filleul en attente la ré-évalue.
  parrainage_resume : ce que le compte voit de son parrainage (code, solde, nombre de filleuls).
*/

insert into public.parrainage_reglages (cle, valeur, description) values
  ('parrainage_fenetre_heures', 168,
   'Un compte ne peut être parrainé que s''il a été créé il y a moins de ce nombre d''heures (évite qu''un compte ancien se fasse parrainer pour rapporter des crédits).'),
  ('parrainage_longueur_code', 8,
   'Nombre de caractères d''un code de parrainage.')
on conflict (cle) do nothing;

/* Un parrain n'est crédité qu'une fois par filleul, même si deux traitements arrivent ensemble. */
create unique index if not exists uq_credits_parrainage_reference
  on public.credits_images_mouvements (user_id, reference)
  where raison = 'parrainage';

create or replace function public.parrainage_generer_code()
returns text
language plpgsql
volatile
set search_path = public
as $$
declare
  v_alphabet constant text := 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
  v_longueur integer;
  v_code text;
  v_i integer;
begin
  select valeur into v_longueur from public.parrainage_reglages where cle = 'parrainage_longueur_code';
  v_longueur := greatest(coalesce(v_longueur, 8), 4);
  loop
    v_code := '';
    for v_i in 1..v_longueur loop
      v_code := v_code || substr(v_alphabet, 1 + floor(random() * length(v_alphabet))::integer, 1);
    end loop;
    exit when not exists (select 1 from public.parrainage_profils where code = v_code);
  end loop;
  return v_code;
end;
$$;

create or replace function public.parrainage_profil_assurer(p_user uuid)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_code text;
  v_email text;
  v_tentatives integer := 0;
begin
  select code into v_code from public.parrainage_profils where user_id = p_user;
  if v_code is not null then
    return v_code;
  end if;

  select email into v_email from auth.users where id = p_user;
  if not found then
    return null;
  end if;

  loop
    begin
      insert into public.parrainage_profils (user_id, code, email_normalise)
      values (p_user, public.parrainage_generer_code(), nullif(public.normaliser_email(v_email), ''));
      exit;
    exception when unique_violation then
      /* Soit le profil vient d'être créé en parallèle, soit deux codes identiques : on reprend. */
      select code into v_code from public.parrainage_profils where user_id = p_user;
      if v_code is not null then
        return v_code;
      end if;
      v_tentatives := v_tentatives + 1;
      if v_tentatives > 5 then
        raise;
      end if;
    end;
  end loop;

  select code into v_code from public.parrainage_profils where user_id = p_user;
  return v_code;
end;
$$;

create or replace function public.parrainage_enregistrer(p_filleul uuid, p_code text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_code text := upper(btrim(coalesce(p_code, '')));
  v_parrain uuid;
  v_ligne public.parrainages%rowtype;
  v_email text;
  v_confirme timestamptz;
  v_cree timestamptz;
  v_fenetre integer;
  v_gain integer;
  v_depart integer;
  v_norm text;
  v_domaine text;
  v_motif text;
  v_lignes integer;
begin
  select email, email_confirmed_at, created_at into v_email, v_confirme, v_cree
    from auth.users where id = p_filleul;
  if not found then
    return jsonb_build_object('statut', 'ignore', 'motif', 'compte_introuvable');
  end if;

  perform public.parrainage_profil_assurer(p_filleul);
  /* Deux appels en même temps pour le même filleul passent l'un après l'autre. */
  perform pg_advisory_xact_lock(hashtext('parrainage:' || p_filleul::text));

  select * into v_ligne from public.parrainages where filleul_id = p_filleul;
  if found then
    if v_ligne.statut <> 'en_attente' then
      return jsonb_build_object('statut', v_ligne.statut, 'motif', v_ligne.motif_refus);
    end if;
  else
    select user_id into v_parrain from public.parrainage_profils where code = v_code;
    if v_parrain is null then
      return jsonb_build_object('statut', 'ignore', 'motif', 'code_inconnu');
    end if;
    if v_parrain = p_filleul then
      return jsonb_build_object('statut', 'ignore', 'motif', 'auto_parrainage');
    end if;
    select valeur into v_fenetre from public.parrainage_reglages where cle = 'parrainage_fenetre_heures';
    v_fenetre := coalesce(v_fenetre, 168);
    if now() - v_cree > make_interval(hours => v_fenetre) then
      return jsonb_build_object('statut', 'ignore', 'motif', 'compte_trop_ancien');
    end if;
    insert into public.parrainages (parrain_id, filleul_id, code_utilise)
    values (v_parrain, p_filleul, v_code)
    returning * into v_ligne;
  end if;

  v_motif := null;
  if v_email is null then
    /* Compte sans email (téléphone) : il n'y a rien à confirmer. */
    v_motif := 'email_non_confirme';
  else
    v_domaine := lower(split_part(v_email, '@', 2));
    if exists (select 1 from public.domaines_email_jetables where domaine = v_domaine) then
      v_motif := 'email_jetable';
    else
      v_norm := public.normaliser_email(v_email);
      /* Même email à une variante près (Gmail : points, +alias) qu'un compte plus ancien. */
      if exists (
        select 1
          from public.parrainage_profils p
          join auth.users u on u.id = p.user_id
         where p.email_normalise = v_norm
           and p.user_id <> p_filleul
           and u.created_at < v_cree
      ) then
        v_motif := 'email_deja_connu';
      end if;
    end if;
  end if;

  if v_motif is not null then
    update public.parrainages set statut = 'refuse', motif_refus = v_motif where id = v_ligne.id;
    return jsonb_build_object('statut', 'refuse', 'motif', v_motif);
  end if;

  if v_confirme is null then
    return jsonb_build_object('statut', 'en_attente', 'motif', null);
  end if;

  update public.parrainages
     set statut = 'valide', valide_a = now()
   where id = v_ligne.id and statut = 'en_attente';

  select valeur into v_gain from public.parrainage_reglages where cle = 'credits_par_filleul';
  v_gain := coalesce(v_gain, 5);
  select valeur into v_depart from public.parrainage_reglages where cle = 'credits_depart';
  v_depart := coalesce(v_depart, 10);

  /* Le parrain n'a peut-être encore jamais généré d'image : sa ligne de crédits est créée avec le solde de départ. */
  insert into public.credits_images (user_id, solde)
  values (v_ligne.parrain_id, v_depart)
  on conflict (user_id) do nothing;
  get diagnostics v_lignes = row_count;
  if v_lignes = 1 then
    insert into public.credits_images_mouvements (user_id, delta, raison)
    values (v_ligne.parrain_id, v_depart, 'depart');
  end if;

  begin
    insert into public.credits_images_mouvements (user_id, delta, raison, reference)
    values (v_ligne.parrain_id, v_gain, 'parrainage', p_filleul::text);
    update public.credits_images
       set solde = solde + v_gain, maj_a = now()
     where user_id = v_ligne.parrain_id;
  exception when unique_violation then
    null; /* déjà crédité pour ce filleul */
  end;

  return jsonb_build_object('statut', 'valide', 'motif', null);
end;
$$;

create or replace function public.parrainage_resume(p_user uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_code text;
  v_solde integer;
  v_depart integer;
  v_valides integer;
  v_attente integer;
begin
  v_code := public.parrainage_profil_assurer(p_user);
  select solde into v_solde from public.credits_images where user_id = p_user;
  if v_solde is null then
    /* Pas encore de ligne : le compte a le solde de départ, la ligne sera créée à la première image. */
    select valeur into v_depart from public.parrainage_reglages where cle = 'credits_depart';
    v_solde := coalesce(v_depart, 10);
  end if;
  select count(*) filter (where statut = 'valide'), count(*) filter (where statut = 'en_attente')
    into v_valides, v_attente
    from public.parrainages where parrain_id = p_user;
  return jsonb_build_object(
    'code', v_code,
    'solde', v_solde,
    'filleuls_valides', v_valides,
    'filleuls_en_attente', v_attente
  );
end;
$$;

revoke all on function public.parrainage_generer_code() from public, anon, authenticated;
revoke all on function public.parrainage_profil_assurer(uuid) from public, anon, authenticated;
revoke all on function public.parrainage_enregistrer(uuid, text) from public, anon, authenticated;
revoke all on function public.parrainage_resume(uuid) from public, anon, authenticated;
grant execute on function public.parrainage_generer_code() to service_role;
grant execute on function public.parrainage_profil_assurer(uuid) to service_role;
grant execute on function public.parrainage_enregistrer(uuid, text) to service_role;
grant execute on function public.parrainage_resume(uuid) to service_role;

/* Les comptes déjà inscrits reçoivent leur code (sans crédits en plus) : ils peuvent eux aussi inviter. */
do $$
declare
  r record;
begin
  for r in
    select u.id from auth.users u
     where not exists (select 1 from public.parrainage_profils p where p.user_id = u.id)
  loop
    perform public.parrainage_profil_assurer(r.id);
  end loop;
end;
$$;
