/*
  Classinus : crédits d'images, fonctions atomiques (étape 2 du parrainage).

  Un crédit est retiré à chaque image générée. Les trois fonctions sont réservées
  au backend (clé secrète Supabase) : aucun utilisateur ne peut les appeler lui-même.

  credits_images_reserver : crée la ligne de crédits d'un compte qui n'en a pas encore
    (solde de départ lu dans parrainage_reglages), puis retire 1 crédit. Renvoie false
    quand le solde est à 0. Le retrait est atomique : deux demandes en même temps ne
    peuvent pas faire passer le solde sous zéro.
  credits_images_rendre : rend le crédit d'une génération, une seule fois par référence.
  credits_images_rattacher : remplace la référence provisoire par l'identifiant de la
    génération Higgsfield, pour pouvoir rembourser plus tard si elle échoue.
*/

/* Un remboursement par référence et par utilisateur, même si deux traitements arrivent ensemble. */
create unique index if not exists uq_credits_remboursement_reference
  on public.credits_images_mouvements (user_id, reference)
  where raison = 'remboursement';

create or replace function public.credits_images_reserver(p_user uuid, p_reference text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_depart integer;
  v_cree integer;
  v_solde integer;
begin
  select valeur into v_depart from public.parrainage_reglages where cle = 'credits_depart';
  v_depart := coalesce(v_depart, 10);

  insert into public.credits_images (user_id, solde)
  values (p_user, v_depart)
  on conflict (user_id) do nothing;
  get diagnostics v_cree = row_count;
  if v_cree = 1 then
    insert into public.credits_images_mouvements (user_id, delta, raison)
    values (p_user, v_depart, 'depart');
  end if;

  update public.credits_images
     set solde = solde - 1, maj_a = now()
   where user_id = p_user and solde > 0
  returning solde into v_solde;
  if v_solde is null then
    return false;
  end if;

  insert into public.credits_images_mouvements (user_id, delta, raison, reference)
  values (p_user, -1, 'generation', p_reference);
  return true;
end;
$$;

create or replace function public.credits_images_rendre(p_user uuid, p_reference text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_reference is null or not exists (
    select 1 from public.credits_images_mouvements
     where user_id = p_user and raison = 'generation' and reference = p_reference
  ) then
    return false;
  end if;

  begin
    insert into public.credits_images_mouvements (user_id, delta, raison, reference)
    values (p_user, 1, 'remboursement', p_reference);
  exception when unique_violation then
    return false;
  end;

  update public.credits_images set solde = solde + 1, maj_a = now() where user_id = p_user;
  return true;
end;
$$;

create or replace function public.credits_images_rattacher(p_user uuid, p_ancienne text, p_nouvelle text)
returns void
language sql
security definer
set search_path = public
as $$
  update public.credits_images_mouvements
     set reference = p_nouvelle
   where user_id = p_user and raison = 'generation' and reference = p_ancienne;
$$;

revoke all on function public.credits_images_reserver(uuid, text) from public, anon, authenticated;
revoke all on function public.credits_images_rendre(uuid, text) from public, anon, authenticated;
revoke all on function public.credits_images_rattacher(uuid, text, text) from public, anon, authenticated;
grant execute on function public.credits_images_reserver(uuid, text) to service_role;
grant execute on function public.credits_images_rendre(uuid, text) to service_role;
grant execute on function public.credits_images_rattacher(uuid, text, text) to service_role;
