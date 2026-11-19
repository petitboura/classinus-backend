/*
  Classinus : parcours de paiement simule de la page Abonnements (19/11/2026, demande de Bourama).

  Apres le clic sur Payer : conditions legales, connexion si besoin, choix du moyen de paiement, petit
  formulaire (WhatsApp, pays), puis un message "preparation de ton abonnement". Aucun paiement n'est pris.

  - liste_attente_modeles : nouvelle colonne moyen_paiement ; le profil devient facultatif (le nouveau
    parcours ne le demande plus).
  - moyens_paiement_liste_attente : les moyens proposes, modifiables sans code (RLS activee, aucune policy,
    seul le backend y accede, comme les autres tables de la liste d'attente).
  - Textes du parcours dans textes_modeles_llm (cles attente_pay_* et attente_moyen_*), francais et anglais.
*/

alter table public.liste_attente_modeles
  add column if not exists moyen_paiement text;

alter table public.liste_attente_modeles
  alter column profil drop not null;

alter table public.liste_attente_modeles
  drop constraint if exists liste_attente_modeles_profil_check;

alter table public.liste_attente_modeles
  add constraint liste_attente_modeles_profil_check
  check (profil is null or profil in ('etudiant', 'administration', 'dev'));

create table if not exists public.moyens_paiement_liste_attente (
  id text primary key check (id ~ '^[a-z0-9_]{1,40}$'),
  ordre integer not null default 0,
  actif boolean not null default true
);

alter table public.moyens_paiement_liste_attente enable row level security;

insert into public.moyens_paiement_liste_attente (id, ordre) values
  ('carte', 1),
  ('orange_money', 2),
  ('wave', 3),
  ('paypal', 4)
on conflict (id) do nothing;

insert into public.textes_modeles_llm (cle, langue, texte) values
  ('attente_pay_legal_titre', 'fr', 'Avant de continuer'),
  ('attente_pay_legal_titre', 'en', 'Before you continue'),
  ('attente_pay_legal_intro', 'fr', 'Tu as choisi le palier {nom} à {prix} $ par mois.'),
  ('attente_pay_legal_intro', 'en', 'You chose the {nom} plan at ${prix} per month.'),
  ('attente_pay_consentement', 'fr', 'J''accepte les conditions d''utilisation et la politique de confidentialité, et que Classinus garde ces informations pour me prévenir quand mon abonnement est prêt.'),
  ('attente_pay_consentement', 'en', 'I accept the terms of use and the privacy policy, and that Classinus keeps this information to let me know when my subscription is ready.'),
  ('attente_pay_lien_cgu', 'fr', 'Lire les conditions d''utilisation'),
  ('attente_pay_lien_cgu', 'en', 'Read the terms of use'),
  ('attente_pay_lien_confidentialite', 'fr', 'Lire la politique de confidentialité'),
  ('attente_pay_lien_confidentialite', 'en', 'Read the privacy policy'),
  ('attente_pay_continuer', 'fr', 'Continuer'),
  ('attente_pay_continuer', 'en', 'Continue'),
  ('attente_pay_retour', 'fr', 'Retour'),
  ('attente_pay_retour', 'en', 'Back'),
  ('attente_pay_fermer', 'fr', 'Fermer'),
  ('attente_pay_fermer', 'en', 'Close'),
  ('attente_pay_connexion_titre', 'fr', 'Connecte-toi pour continuer'),
  ('attente_pay_connexion_titre', 'en', 'Sign in to continue'),
  ('attente_pay_connexion_detail', 'fr', 'Il te faut un compte Classinus pour préparer ton abonnement. Tes choix sont gardés, tu reviens ici juste après.'),
  ('attente_pay_connexion_detail', 'en', 'You need a Classinus account to prepare your subscription. Your choices are kept and you come back here right after.'),
  ('attente_pay_creer_compte', 'fr', 'Créer un compte'),
  ('attente_pay_creer_compte', 'en', 'Create an account'),
  ('attente_pay_se_connecter', 'fr', 'Déjà un compte ? Se connecter'),
  ('attente_pay_se_connecter', 'en', 'Already have an account? Sign in'),
  ('attente_pay_moyen_titre', 'fr', 'Comment veux-tu payer ?'),
  ('attente_pay_moyen_titre', 'en', 'How do you want to pay?'),
  ('attente_moyen_carte', 'fr', 'Carte bancaire'),
  ('attente_moyen_carte', 'en', 'Bank card'),
  ('attente_moyen_orange_money', 'fr', 'Orange Money'),
  ('attente_moyen_orange_money', 'en', 'Orange Money'),
  ('attente_moyen_wave', 'fr', 'Wave'),
  ('attente_moyen_wave', 'en', 'Wave'),
  ('attente_moyen_paypal', 'fr', 'PayPal'),
  ('attente_moyen_paypal', 'en', 'PayPal'),
  ('attente_pay_form_titre', 'fr', 'Dernière étape'),
  ('attente_pay_form_titre', 'en', 'Last step'),
  ('attente_pay_form_detail', 'fr', 'Dis-nous où te prévenir quand ton abonnement est prêt.'),
  ('attente_pay_form_detail', 'en', 'Tell us where to reach you when your subscription is ready.'),
  ('attente_pay_pays_label', 'fr', 'Pays'),
  ('attente_pay_pays_label', 'en', 'Country'),
  ('attente_pay_whatsapp_label', 'fr', 'Numéro WhatsApp'),
  ('attente_pay_whatsapp_label', 'en', 'WhatsApp number'),
  ('attente_pay_envoyer', 'fr', 'Valider'),
  ('attente_pay_envoyer', 'en', 'Confirm'),
  ('attente_pay_merci_titre', 'fr', 'Préparation de ton abonnement'),
  ('attente_pay_merci_titre', 'en', 'Preparing your subscription'),
  ('attente_pay_merci_detail', 'fr', 'On prépare ton abonnement {nom}. Tu seras prévenu sur WhatsApp dès qu''il est prêt. Aucun paiement n''a été pris pour l''instant.'),
  ('attente_pay_merci_detail', 'en', 'We are preparing your {nom} subscription. You will be told on WhatsApp as soon as it is ready. No payment has been taken for now.')
on conflict (cle, langue) do update set texte = excluded.texte, updated_at = now();
