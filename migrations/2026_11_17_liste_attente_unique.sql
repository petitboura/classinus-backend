/*
  Liste d'attente unique (17/11/2026, demande de Bourama) : une seule inscription par utilisateur,
  pas une par modele. La colonne modele_id garde le modele sur lequel la personne a clique en
  s'inscrivant (le modele d'origine). Ajoute aussi les noms des paliers (Pro, Max, Ultra), les
  points de chaque palier et les textes mis a jour pour une liste unique.
*/

-- Une ligne par utilisateur : on garde la plus recente (derniers choix) et on retire les autres.
delete from public.liste_attente_modeles a
using public.liste_attente_modeles b
where a.user_id = b.user_id
  and (a.modifie_a, a.id) < (b.modifie_a, b.id);

alter table public.liste_attente_modeles
  drop constraint if exists liste_attente_modeles_user_id_modele_id_key;

alter table public.liste_attente_modeles
  add constraint liste_attente_modeles_user_id_key unique (user_id);

/* Textes : {nom} est le nom du palier, {prix} son prix. Remplace les textes de la version par modele. */
insert into public.textes_modeles_llm (cle, langue, texte) values
  ('attente_intro', 'fr', 'Les modèles Claude, GPT et Gemini arrivent sur Classinus. Choisis ton palier, on te prévient dès l''ouverture.'),
  ('attente_intro', 'en', 'Claude, GPT and Gemini models are coming to Classinus. Pick your plan and we will let you know when they open.'),
  ('attente_merci_detail', 'fr', 'On te prévient dès l''ouverture. Aucun paiement n''a été pris.'),
  ('attente_merci_detail', 'en', 'We will let you know as soon as it opens. No payment was taken.'),
  ('attente_deja_inscrit', 'fr', 'Tu es déjà sur la liste d''attente, avec le palier {nom} à {prix} $ par mois.'),
  ('attente_deja_inscrit', 'en', 'You are already on the waiting list, with the {nom} plan at ${prix} per month.'),
  ('attente_desinscrit', 'fr', 'Tu es retiré de la liste d''attente.'),
  ('attente_desinscrit', 'en', 'You have been removed from the waiting list.'),
  ('attente_palier_nom_10', 'fr', 'Pro'),
  ('attente_palier_nom_10', 'en', 'Pro'),
  ('attente_palier_nom_17', 'fr', 'Max'),
  ('attente_palier_nom_17', 'en', 'Max'),
  ('attente_palier_nom_20', 'fr', 'Ultra'),
  ('attente_palier_nom_20', 'en', 'Ultra'),
  ('attente_palier_20', 'fr', 'Comme Max, avec plus de crédit et une exécution de code quasi illimitée.'),
  ('attente_palier_20', 'en', 'Like Max, with more credit and nearly unlimited code execution.'),
  ('attente_palier_par_mois', 'fr', 'par mois'),
  ('attente_palier_par_mois', 'en', 'per month'),
  ('attente_palier_10_points', 'fr', 'Recherche, bibliothèque, skills et pédagogie sans limite|Sans accès aux plus grands modèles|Connecteurs et exécution de code limités|OCR sans limite'),
  ('attente_palier_10_points', 'en', 'Unlimited search, library, skills and learning tools|No access to the largest models|Limited connectors and code execution|Unlimited OCR'),
  ('attente_palier_17_points', 'fr', 'Tous les groupes de modèles avec ton crédit|Connecteurs et exécution de code illimités|Agent navigateur et ordinateur|Voix en direct, vidéos YouTube et exploration web profonde'),
  ('attente_palier_17_points', 'en', 'Every model group with your credit|Unlimited connectors and code execution|Browser and computer agent|Live voice, YouTube videos and deep web exploration'),
  ('attente_palier_20_points', 'fr', 'Tout ce que contient Max|Plus de crédit de modèles chaque mois|Exécution de code quasi illimitée'),
  ('attente_palier_20_points', 'en', 'Everything in Max|More model credit every month|Nearly unlimited code execution')
on conflict (cle, langue) do update set texte = excluded.texte, updated_at = now();
