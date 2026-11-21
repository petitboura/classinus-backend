/*
  21/11/2026, demande de Bourama (appliquee d'abord sur le staging) : les pastilles des entreprises de la page
  /abonnements deviennent des boutons. Texte lu par les lecteurs d'ecran, francais et anglais. {nom} = entreprise.
  Idempotente.
*/
insert into public.textes_modeles_llm (cle, langue, texte) values
  ('attente_entreprises_aller', 'fr', 'Voir les modèles de {nom}'),
  ('attente_entreprises_aller', 'en', 'See the {nom} models')
on conflict (cle, langue) do update set texte = excluded.texte, updated_at = now();
