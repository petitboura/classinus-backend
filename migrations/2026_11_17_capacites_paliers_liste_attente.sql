/*
  Classinus : capacites de chaque palier de la liste d'attente (17/11/2026, retour de Bourama).

  Les cartes de palier du formulaire (CartePalierListeAttente.tsx) lisent leurs points dans
  attente_palier_<prix>_points, separes par « | ». Ces textes avaient ete ecrits directement dans la base
  de Staging, sans migration, et ne citaient pas bien les capacites de chaque palier : « productivite » et
  « documents » manquaient au palier 1, rien ne disait qu'il n'a ni agent navigateur ni voix en direct, et
  Higgsfield n'apparaissait nulle part. Le texte de secours du palier 1 disait « agent navigateur limite »
  alors que le document de Bourama dit « Non ».

  Source unique : le tableau « Fonctionnalites par palier » du document « Classinus : liste d'attente,
  paliers et credits » (decisions du 16/11/2026). Les trois cartes citent maintenant les memes capacites,
  dans le meme ordre, pour que chaque palier se compare d'un coup d'oeil. Un point qui commence par « ~ »
  est une capacite que le palier n'a pas (croix grisee au lieu d'une coche).

  Le credit mensuel (8, 15 et 17 $) n'est pas dans les points : la carte l'affiche a part, depuis la table
  paliers_liste_attente. A appliquer apres 2026_11_16_liste_attente_modeles.sql.
*/

insert into public.textes_modeles_llm (cle, langue, texte) values
  ('attente_palier_par_mois', 'fr', 'par mois'),
  ('attente_palier_par_mois', 'en', 'per month'),

  ('attente_palier_10_points', 'fr', 'Recherche, bibliothèque, skills, pédagogie, productivité et documents illimités|OCR sans limite|Connecteurs restreints|Exécution de code restreinte|~Sans accès aux plus grands modèles|~Sans agent navigateur et ordinateur|~Sans voix en direct, lecture de vidéos YouTube ni exploration web profonde|~Audio, image, vidéo et 3D (Higgsfield) : bientôt'),
  ('attente_palier_10_points', 'en', 'Unlimited search, library, skills, teaching, productivity and documents|Unlimited OCR|Limited connectors|Limited code execution|~No access to the largest models|~No browser and computer agent|~No live voice, YouTube video reading or deep web exploration|~Audio, image, video and 3D (Higgsfield): coming soon'),

  ('attente_palier_17_points', 'fr', 'Recherche, bibliothèque, skills, pédagogie, productivité et documents illimités|OCR sans limite|Connecteurs illimités|Exécution de code illimitée|Accès aux plus grands modèles, avec ton crédit|Agent navigateur et ordinateur|Voix en direct, lecture de vidéos YouTube et exploration web profonde|~Audio, image, vidéo et 3D (Higgsfield) : bientôt'),
  ('attente_palier_17_points', 'en', 'Unlimited search, library, skills, teaching, productivity and documents|Unlimited OCR|Unlimited connectors|Unlimited code execution|Access to the largest models, using your credit|Browser and computer agent|Live voice, YouTube video reading and deep web exploration|~Audio, image, video and 3D (Higgsfield): coming soon'),

  ('attente_palier_20_points', 'fr', 'Recherche, bibliothèque, skills, pédagogie, productivité et documents illimités|OCR sans limite|Connecteurs illimités|Exécution de code quasi illimitée|Accès aux plus grands modèles, avec ton crédit|Agent navigateur et ordinateur|Voix en direct, lecture de vidéos YouTube et exploration web profonde|~Audio, image, vidéo et 3D (Higgsfield) : bientôt'),
  ('attente_palier_20_points', 'en', 'Unlimited search, library, skills, teaching, productivity and documents|Unlimited OCR|Unlimited connectors|Nearly unlimited code execution|Access to the largest models, using your credit|Browser and computer agent|Live voice, YouTube video reading and deep web exploration|~Audio, image, video and 3D (Higgsfield): coming soon'),

  /* Textes de secours, affiches seulement si les points d'un palier manquent. */
  ('attente_palier_10', 'fr', 'Sans accès aux plus grands modèles et sans agent navigateur et ordinateur. Connecteurs et exécution de code restreints.'),
  ('attente_palier_10', 'en', 'No access to the largest models and no browser and computer agent. Connectors and code execution are limited.'),
  ('attente_palier_17', 'fr', 'Accès aux plus grands modèles avec ton crédit, connecteurs et exécution de code illimités, agent navigateur et ordinateur.'),
  ('attente_palier_17', 'en', 'Access to the largest models using your credit, unlimited connectors and code execution, browser and computer agent.')
on conflict (cle, langue) do update set texte = excluded.texte, updated_at = now();
