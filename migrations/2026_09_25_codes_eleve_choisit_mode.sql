-- Controle enseignant sur le selecteur de mode eleve (25/09/2026, demande
-- Bourama) : un enseignant peut desormais retirer a l'eleve le choix de
-- son mode source et de son mode pedagogique pour un code donne. Voir
-- core/codes_partage.py (creer_code/modifier_code/lister_mes_rattachements),
-- api/codes_partage.py (CodePayload/CodePatchPayload) et le nouvel outil
-- core/outils_changement_mode.py (changer_mode_conversation).
--
-- Cochee par defaut (true) : rien ne change pour les codes existants tant
-- que l'enseignant ne la decoche pas explicitement.

alter table codes_partage
  add column if not exists eleve_choisit_mode boolean not null default true;
