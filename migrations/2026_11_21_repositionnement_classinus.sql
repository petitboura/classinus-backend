/*
  Repositionnement Classinus — catégories de capacités de l'espace Abonnements.
  Les nouvelles catégories placent les modèles, intégrations et agents au centre
  de la présentation. Les outils pédagogiques restent disponibles comme usage
  spécifique, sans définir l'identité globale du produit.

  Cette mise à jour de données a été appliquée au projet Supabase Classinus Staging
  (prchrczmcoqngesbzzfi) le 21/11/2026. Ne pas appliquer à la production sans validation.
*/
insert into public.textes_modeles_llm (cle, langue, texte) values
  ('attente_cap_titre', 'fr', 'L''IA et tes outils, réunis dans un même espace'),
  ('attente_cap_titre', 'en', 'AI and your tools, in one workspace'),
  ('attente_cap_ordre', 'fr', 'ia|connecteurs|agents|programmer|documents|recherche|bibliotheque|plateformes|media|etudier'),
  ('attente_cap_ordre', 'en', 'ia|connecteurs|agents|programmer|documents|recherche|bibliotheque|plateformes|media|etudier'),

  ('attente_cap_ia_titre', 'fr', 'Modèles et assistants IA'),
  ('attente_cap_ia_titre', 'en', 'AI models and assistants'),

  ('attente_cap_connecteurs_titre', 'fr', 'Applications et intégrations'),
  ('attente_cap_connecteurs_titre', 'en', 'Connected apps and integrations'),
  ('attente_cap_connecteurs_lignes', 'fr', 'GitHub|Notion|Vercel|Railway|Supabase|Higgsfield|Tes propres outils via des serveurs MCP'),
  ('attente_cap_connecteurs_lignes', 'en', 'GitHub|Notion|Vercel|Railway|Supabase|Higgsfield|Your own tools through MCP servers'),

  ('attente_cap_agents_titre', 'fr', 'Agents et automatisation'),
  ('attente_cap_agents_titre', 'en', 'Agents and automation'),
  ('attente_cap_agents_lignes', 'fr', 'Création et configuration d''agents IA|Consignes et comportements personnalisés|Skills réutilisables avec leurs fichiers|Mémoire consultable et modifiable|Procédures, règles et styles personnalisés'),
  ('attente_cap_agents_lignes', 'en', 'Create and configure AI agents|Custom instructions and behaviors|Reusable skills and their files|Reviewable and editable memory|Custom procedures, rules, and styles'),

  ('attente_cap_programmer_titre', 'fr', 'Développer et exécuter du code'),
  ('attente_cap_programmer_titre', 'en', 'Develop and run code'),

  ('attente_cap_documents_titre', 'fr', 'Créer des documents et des fichiers'),
  ('attente_cap_documents_titre', 'en', 'Create documents and files'),

  ('attente_cap_recherche_titre', 'fr', 'Recherche et ressources'),
  ('attente_cap_recherche_titre', 'en', 'Search and resources'),

  ('attente_cap_bibliotheque_titre', 'fr', 'Documents, bibliothèque et mémoire'),
  ('attente_cap_bibliotheque_titre', 'en', 'Documents, library, and memory'),
  ('attente_cap_bibliotheque_lignes', 'fr', 'Import de fichiers, de liens et de textes|Dossiers et sous-dossiers|Recherche dans tes documents|Bibliothèque publique partagée par la communauté|Mémoire personnelle de l''IA|Skills personnalisés|Catalogue public de skills'),
  ('attente_cap_bibliotheque_lignes', 'en', 'Import files, links, and text|Folders and subfolders|Search your documents|Public library shared by the community|Personal AI memory|Custom skills|Public skills catalog'),

  ('attente_cap_plateformes_titre', 'fr', 'Sur le web et tes appareils'),
  ('attente_cap_plateformes_titre', 'en', 'On the web and your devices'),

  ('attente_cap_etudier_titre', 'fr', 'Apprendre et s''organiser'),
  ('attente_cap_etudier_titre', 'en', 'Learning and organization')
on conflict (cle, langue)
do update set texte = excluded.texte, updated_at = now();
