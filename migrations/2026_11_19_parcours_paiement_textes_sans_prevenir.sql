/*
  Classinus : parcours de paiement simule (19/11/2026, demande de Bourama). Avant la fin du parcours, on ne
  dit pas a la personne qu'elle sera prevenue quand l'abonnement sera pret : ce message n'apparait qu'a
  l'ecran final. Le texte du formulaire et celui du consentement donnent donc une autre raison (finaliser
  l'abonnement, le gerer et la contacter).
*/
insert into public.textes_modeles_llm (cle, langue, texte) values
  ('attente_pay_form_detail', 'fr', 'On a besoin de ces informations pour finaliser ton abonnement.'),
  ('attente_pay_form_detail', 'en', 'We need this information to finalize your subscription.'),
  ('attente_pay_consentement', 'fr', 'J''accepte les conditions d''utilisation et la politique de confidentialité, et que Classinus garde ces informations pour gérer mon abonnement et me contacter.'),
  ('attente_pay_consentement', 'en', 'I accept the terms of use and the privacy policy, and that Classinus keeps this information to manage my subscription and contact me.')
on conflict (cle, langue) do update set texte = excluded.texte, updated_at = now();
