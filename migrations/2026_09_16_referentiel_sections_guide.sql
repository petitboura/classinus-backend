-- Etape 1 du chantier "guide de decouverte" (voir specs-guide-decouverte.md
-- dans clovis-frontend), demande Bourama, 16/09/2026.
--
-- Referentiel des sections presentees a l'utilisateur dans le guide
-- interactif de Clovis. Fait le lien entre un article de la base de
-- connaissance (table public.documents, agent_id = 'clovis') et le
-- libelle/accroche affiches a l'utilisateur, qui ne doit jamais voir les
-- noms de fichiers techniques des articles.
--
-- Etape independante : rien ne consomme encore cette table (l'etape 2,
-- le mode de conversation "guide", et l'etape 3, l'instruction de prompt,
-- ne sont pas encore poussees). Aucune dependance a autre chose que la
-- table existante public.documents, dont le contenu n'est pas modifie ici.
--
-- ATTENTION NOM : ne pas confondre avec conversation_mode_actif (mode
-- eleve/enseignant rattache a un code de classe) ni avec un futur mode de
-- conversation "guide" (etape 2) : cette table ne stocke qu'un referentiel
-- de contenu statique par section, pas un etat de conversation.

CREATE TABLE IF NOT EXISTS public.guide_sections (
    nom_article text PRIMARY KEY,
    libelle_utilisateur text NOT NULL,
    accroche_courte text NOT NULL,
    ordre integer NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_guide_sections_ordre
    ON public.guide_sections USING btree (ordre);

ALTER TABLE public.guide_sections ENABLE ROW LEVEL SECURITY;
-- Aucune policy definie : accès exclusivement via la clé service_role
-- (backend), même logique que conversation_persona_pedagogique et
-- historique_reponses_qcm.

INSERT INTO public.guide_sections (nom_article, libelle_utilisateur, accroche_courte, ordre) VALUES
('01-vue-ensemble.md', 'Vue d''ensemble', 'Ce que Clovis peut faire pour toi, en un coup d''oeil.', 1),
('02-chat.md', 'Le chat', 'La conversation avec Clovis et ses outils.', 2),
('03-generation.md', 'Génération de contenus', 'Documents, code, images, audio, vidéo et plus.', 3),
('04-recherche-et-connecteurs.md', 'Recherche et connecteurs', 'Recherche web et services externes connectés.', 4),
('05-bibliotheque.md', 'Bibliothèque personnelle', 'Tes fichiers, retrouvables dans toutes tes conversations.', 5),
('06-memoire-et-profil.md', 'Mémoire et profil', 'Ce que Clovis retient de toi au fil du temps.', 6),
('07-skills.md', 'Skills', 'Des instructions personnelles que tu donnes à Clovis.', 7),
('08-base-de-connaissance.md', 'Base de connaissance de Clovis', 'Comment Clovis connaît sa propre application.', 8),
('09-bureau-enseignant.md', 'Bureau (enseignant)', 'Les outils destinés aux enseignants.', 9),
('10-avancement-programme.md', 'Programme et avancement', 'Le suivi des notions vues en classe.', 10),
('11-telephone.md', 'Dossiers du téléphone', 'Retrouver des fichiers stockés sur ton appareil.', 11),
('12-utilitaires.md', 'Utilitaires du chat', 'Position, formules, dessin et autres raccourcis.', 12),
('13-outils-dynamiques.md', 'Outils dynamiques', 'Comment Clovis va chercher un outil qui lui manque.', 13),
('14-connecter-claude.md', 'Connecter Clovis dans Claude', 'Utiliser Clovis depuis l''assistant Claude.', 14),
('15-concentration.md', 'Concentration', 'Gérer son temps de travail et les distractions.', 15),
('16-integrations-externes.md', 'Intégrations externes', 'GitHub, Notion, Google Drive et les autres services.', 16),
('17-capacites-ia.md', 'Ce que Clovis sait faire', 'Les capacités de Clovis en tant qu''IA, en résumé.', 17)
ON CONFLICT (nom_article) DO UPDATE SET
    libelle_utilisateur = EXCLUDED.libelle_utilisateur,
    accroche_courte = EXCLUDED.accroche_courte,
    ordre = EXCLUDED.ordre;
