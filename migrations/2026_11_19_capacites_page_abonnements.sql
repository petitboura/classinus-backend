/*
  Classinus : capacites par categorie de la page des abonnements (19/11/2026, demande de Bourama).

  La page /abonnements (components/abonnements/PageAbonnements.tsx) montre maintenant, au-dessus des
  paliers, ce que Classinus sait faire, regroupe en categories repliables. Rien n'est ecrit dans le
  code du front : tout vient de textes_modeles_llm, en francais et en anglais, par ces cles :

  - attente_cap_titre : titre de la section.
  - attente_cap_ordre : identifiants des categories, dans l'ordre d'affichage, separes par « | ».
  - attente_cap_<id>_titre : titre de la categorie.
  - attente_cap_<id>_lignes : une capacite par ligne, separees par « | ». Une ligne qui commence par
    « ~ » est une capacite pas encore ouverte (elle porte l'etiquette attente_cap_bientot). La ligne
    speciale « @modeles » place ici le tableau des modeles, lu depuis modeles_llm et fournisseurs_llm.
  - attente_cap_bientot : etiquette des capacites pas encore ouvertes.

  Pour ajouter, retirer ou renommer une categorie ou une ligne : modifier ces textes dans Supabase, sans
  toucher au code. Le choix des categories vient de l'audit fonctionnel du 15/11/2026. Les capacites
  d'image, de video, de son et de 3D suivent le tableau des paliers (decisions du 16/11/2026) : « bientot ».
  A appliquer apres 2026_11_17_capacites_paliers_liste_attente.sql.
*/

insert into public.textes_modeles_llm (cle, langue, texte) values
  ('attente_cap_titre', 'fr', 'Ce que tu peux faire avec Classinus'),
  ('attente_cap_titre', 'en', 'What you can do with Classinus'),
  ('attente_cap_bientot', 'fr', 'Bientôt'),
  ('attente_cap_bientot', 'en', 'Coming soon'),
  ('attente_cap_ordre', 'fr', 'ia|recherche|documents|media|bibliotheque|etudier|plateformes|programmer|connecteurs'),
  ('attente_cap_ordre', 'en', 'ia|recherche|documents|media|bibliotheque|etudier|plateformes|programmer|connecteurs'),

  ('attente_cap_ia_titre', 'fr', 'Assistant IA'),
  ('attente_cap_ia_titre', 'en', 'AI assistant'),
  ('attente_cap_ia_lignes', 'fr', 'Conversations avec l''IA de ton choix|Choix du modèle depuis la liste ci-dessous|Réglage de la profondeur de réflexion selon le modèle|Réponses affichées au fur et à mesure|Historique des conversations et reprise après une coupure|Régénération d''une réponse|Outils utilisés par l''IA pendant la conversation|Confirmation avant les actions sensibles|@modeles'),
  ('attente_cap_ia_lignes', 'en', 'Conversations with the AI of your choice|Pick the model from the list below|Reasoning depth setting, depending on the model|Answers shown as they are written|Conversation history and resuming after an interruption|Regenerating an answer|Tools used by the AI during the conversation|Confirmation before sensitive actions|@modeles'),

  ('attente_cap_recherche_titre', 'fr', 'Recherche et sources'),
  ('attente_cap_recherche_titre', 'en', 'Search and sources'),
  ('attente_cap_recherche_lignes', 'fr', 'Recherche sur le web|Recherche d''images et de vidéos|Articles scientifiques et publications ouvertes|Livres numériques et documents d''archives|Lecture de PDF et de documents scannés (OCR)|Retrouver les passages utiles dans tes documents|Réponses appuyées sur des sources'),
  ('attente_cap_recherche_lignes', 'en', 'Web search|Image and video search|Scientific articles and open publications|E-books and archive documents|Reading PDFs and scanned documents (OCR)|Finding the useful passages in your documents|Answers backed by sources'),

  ('attente_cap_documents_titre', 'fr', 'Créer des documents'),
  ('attente_cap_documents_titre', 'en', 'Create documents'),
  ('attente_cap_documents_lignes', 'fr', 'PDF, Word, Excel et PowerPoint|Documents LaTeX|Export de données en CSV et JSON|Calcul formel|Sites web simples|Projets de code en archive ZIP|Fichiers créés enregistrés dans ta bibliothèque'),
  ('attente_cap_documents_lignes', 'en', 'PDF, Word, Excel and PowerPoint|LaTeX documents|Data export as CSV and JSON|Symbolic computation|Simple websites|Code projects as a ZIP archive|Created files saved in your library'),

  ('attente_cap_media_titre', 'fr', 'Images, vidéos et sons'),
  ('attente_cap_media_titre', 'en', 'Images, videos and sounds'),
  ('attente_cap_media_lignes', 'fr', '~Création d''images|~Création de vidéos|~Voix de synthèse|~Modèles 3D|~Espace Higgsfield : vidéo, image et Marketing Studio'),
  ('attente_cap_media_lignes', 'en', '~Image creation|~Video creation|~Synthetic voice|~3D models|~Higgsfield space: video, image and Marketing Studio'),

  ('attente_cap_bibliotheque_titre', 'fr', 'Bibliothèque et mémoire'),
  ('attente_cap_bibliotheque_titre', 'en', 'Library and memory'),
  ('attente_cap_bibliotheque_lignes', 'fr', 'Import de fichiers, de liens et de textes|Dossiers et sous-dossiers|Recherche dans tes documents|Bibliothèque publique partagée|Mémoire personnelle de l''IA|Skills personnalisés|Catalogue public de skills'),
  ('attente_cap_bibliotheque_lignes', 'en', 'Importing files, links and texts|Folders and subfolders|Search in your documents|Shared public library|Personal memory for the AI|Custom skills|Public skills catalog'),

  ('attente_cap_etudier_titre', 'fr', 'Étudier et s''organiser'),
  ('attente_cap_etudier_titre', 'en', 'Study and get organized'),
  ('attente_cap_etudier_lignes', 'fr', 'Modes pédagogiques|QCM et suivi de progression par notion|Rappels et minuteurs|Sessions de concentration sur Android|Notifications'),
  ('attente_cap_etudier_lignes', 'en', 'Teaching modes|Quizzes and progress tracking by topic|Reminders and timers|Focus sessions on Android|Notifications'),

  ('attente_cap_plateformes_titre', 'fr', 'Partout avec toi'),
  ('attente_cap_plateformes_titre', 'en', 'Everywhere you go'),
  ('attente_cap_plateformes_lignes', 'fr', 'Sur le web, dans ton navigateur|Application Android|Application Windows'),
  ('attente_cap_plateformes_lignes', 'en', 'On the web, in your browser|Android app|Windows app'),

  ('attente_cap_programmer_titre', 'fr', 'Programmer'),
  ('attente_cap_programmer_titre', 'en', 'Programming'),
  ('attente_cap_programmer_lignes', 'fr', 'Exécution de code dans un espace isolé|Fichiers de travail par conversation|Modification de projets existants|Mise en ligne de sites'),
  ('attente_cap_programmer_lignes', 'en', 'Running code in an isolated workspace|Working files for each conversation|Editing existing projects|Putting websites online'),

  ('attente_cap_connecteurs_titre', 'fr', 'Applications connectées'),
  ('attente_cap_connecteurs_titre', 'en', 'Connected apps'),
  ('attente_cap_connecteurs_lignes', 'fr', 'GitHub|Notion|Google : Drive, Gmail, Docs, Sheets et Agenda|Vercel et Supabase|Tes propres outils, par serveur MCP'),
  ('attente_cap_connecteurs_lignes', 'en', 'GitHub|Notion|Google: Drive, Gmail, Docs, Sheets and Calendar|Vercel and Supabase|Your own tools, through an MCP server')
on conflict (cle, langue) do update set texte = excluded.texte, updated_at = now();
