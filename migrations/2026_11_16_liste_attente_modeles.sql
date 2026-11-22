/*
  Classinus : liste d'attente des modeles "Bientot" (16/11/2026, demande de Bourama).

  Une fausse porte mesure la demande reelle avant de brancher Claude, GPT et Gemini : un clic sur
  un modele grise du selecteur ouvre un formulaire d'inscription. Aucun paiement n'est pris.

  Quatre tables :
  - paliers_liste_attente : les paliers proposes (prix et credit mensuel), modifiables sans code.
  - liste_attente_modeles : une ligne par utilisateur et par modele clique.
  - evenements_liste_attente : les quatre etapes de l'entonnoir, pour les chiffres investisseurs.
  - Les textes du formulaire vont dans textes_modeles_llm (cle attente_*), en francais et en anglais.

  RLS activee et AUCUNE policy volontairement : seul le backend (cle secrete Supabase) y accede,
  comme pour les autres tables sensibles. Les lignes liees a un compte ont ON DELETE CASCADE vers
  auth.users et sont aussi dans core/purge_compte.py et dans l'export des donnees.
*/

create table if not exists public.paliers_liste_attente (
  prix_usd integer primary key check (prix_usd > 0),
  credit_usd integer not null check (credit_usd > 0),
  ordre integer not null default 0,
  actif boolean not null default true
);

insert into public.paliers_liste_attente (prix_usd, credit_usd, ordre) values
  (10, 8, 1),
  (17, 15, 2),
  (20, 17, 3)
on conflict (prix_usd) do nothing;

create table if not exists public.liste_attente_modeles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  email text,
  modele_id text not null,
  palier_prix integer not null references public.paliers_liste_attente(prix_usd),
  profil text not null check (profil in ('etudiant', 'administration', 'dev')),
  pays text,
  whatsapp text,
  langue text,
  source text,
  consentement boolean not null check (consentement),
  consentement_le timestamptz not null default now(),
  statut text not null default 'actif'
    check (statut in ('actif', 'desinscrit', 'suppression_demandee')),
  cree_a timestamptz not null default now(),
  modifie_a timestamptz not null default now(),
  unique (user_id, modele_id)
);

create index if not exists idx_liste_attente_modele
  on public.liste_attente_modeles (modele_id, palier_prix);

create table if not exists public.evenements_liste_attente (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  etape text not null
    check (etape in ('selecteur_ouvert', 'modele_grise_clique', 'formulaire_ouvert', 'inscription_validee')),
  modele_id text,
  langue text,
  source text,
  cree_a timestamptz not null default now()
);

create index if not exists idx_evenements_liste_attente
  on public.evenements_liste_attente (etape, cree_a desc);

alter table public.paliers_liste_attente enable row level security;
alter table public.liste_attente_modeles enable row level security;
alter table public.evenements_liste_attente enable row level security;

/* Textes du formulaire, francais et anglais. {modele}, {prix} et {credit} sont remplaces par l'appli. */
insert into public.textes_modeles_llm (cle, langue, texte) values
  ('bientot', 'en', 'Coming soon'),
  ('attente_titre', 'fr', 'Rejoins la liste d''attente'),
  ('attente_titre', 'en', 'Join the waiting list'),
  ('attente_intro', 'fr', '{modele} arrive bientôt sur Classinus. Dis-nous ce qui t''intéresse, on te prévient dès l''ouverture.'),
  ('attente_intro', 'en', '{modele} is coming soon to Classinus. Tell us what you are interested in and we will let you know when it opens.'),
  ('attente_aucun_paiement', 'fr', 'Aucun paiement n''est pris pour l''instant. Les prix sont prévisionnels et peuvent changer.'),
  ('attente_aucun_paiement', 'en', 'No payment is taken for now. Prices are estimates and may change.'),
  ('attente_palier_label', 'fr', 'Choisis un palier'),
  ('attente_palier_label', 'en', 'Choose a plan'),
  ('attente_palier_prix', 'fr', '{prix} $ par mois'),
  ('attente_palier_prix', 'en', '${prix} per month'),
  ('attente_palier_credit', 'fr', '{credit} $ de crédit de modèles par mois'),
  ('attente_palier_credit', 'en', '${credit} of model credit per month'),
  ('attente_palier_10', 'fr', 'Sans accès aux plus grands modèles. Connecteurs et agent navigateur limités.'),
  ('attente_palier_10', 'en', 'No access to the largest models. Connectors and the browser agent are limited.'),
  ('attente_palier_17', 'fr', 'Tous les groupes de modèles avec ton crédit, connecteurs illimités, agent navigateur et ordinateur.'),
  ('attente_palier_17', 'en', 'Every model group with your credit, unlimited connectors, browser and computer agent.'),
  ('attente_palier_20', 'fr', 'Comme le palier à 17 $, avec plus de crédit et une exécution de code quasi illimitée.'),
  ('attente_palier_20', 'en', 'Like the $17 plan, with more credit and nearly unlimited code execution.'),
  ('attente_profil_label', 'fr', 'Tu es'),
  ('attente_profil_label', 'en', 'You are'),
  ('attente_profil_etudiant', 'fr', 'Étudiant'),
  ('attente_profil_etudiant', 'en', 'Student'),
  ('attente_profil_administration', 'fr', 'Administration'),
  ('attente_profil_administration', 'en', 'Administration'),
  ('attente_profil_dev', 'fr', 'Développeur'),
  ('attente_profil_dev', 'en', 'Developer'),
  ('attente_pays_label', 'fr', 'Pays (facultatif)'),
  ('attente_pays_label', 'en', 'Country (optional)'),
  ('attente_whatsapp_label', 'fr', 'WhatsApp (facultatif)'),
  ('attente_whatsapp_label', 'en', 'WhatsApp (optional)'),
  ('attente_consentement', 'fr', 'J''accepte que Classinus garde ces informations pour me prévenir de l''ouverture.'),
  ('attente_consentement', 'en', 'I agree that Classinus keeps this information to let me know when it opens.'),
  ('attente_donnees', 'fr', 'Tes réponses servent uniquement à mesurer l''intérêt et à te prévenir. Tu peux te désinscrire ou demander la suppression à tout moment.'),
  ('attente_donnees', 'en', 'Your answers are only used to measure interest and to notify you. You can unsubscribe or ask for deletion at any time.'),
  ('attente_valider', 'fr', 'Rejoindre la liste'),
  ('attente_valider', 'en', 'Join the list'),
  ('attente_merci_titre', 'fr', 'C''est noté'),
  ('attente_merci_titre', 'en', 'You are on the list'),
  ('attente_merci_detail', 'fr', 'On te prévient dès que {modele} ouvre. Aucun paiement n''a été pris.'),
  ('attente_merci_detail', 'en', 'We will let you know as soon as {modele} opens. No payment was taken.'),
  ('attente_deja_inscrit', 'fr', 'Tu es déjà inscrit pour {modele} avec le palier à {prix} $ par mois.'),
  ('attente_deja_inscrit', 'en', 'You are already on the list for {modele} with the ${prix} per month plan.'),
  ('attente_modifier', 'fr', 'Modifier mon choix'),
  ('attente_modifier', 'en', 'Change my choice'),
  ('attente_desinscrire', 'fr', 'Me désinscrire'),
  ('attente_desinscrire', 'en', 'Unsubscribe'),
  ('attente_desinscrit', 'fr', 'Tu es désinscrit de la liste pour {modele}.'),
  ('attente_desinscrit', 'en', 'You have been removed from the list for {modele}.'),
  ('attente_fermer', 'fr', 'Fermer'),
  ('attente_fermer', 'en', 'Close')
on conflict (cle, langue) do nothing;
