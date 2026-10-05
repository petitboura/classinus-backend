-- 04/10/2026, demande Bourama : un element (skill, regle, procedure,
-- comportement, style) LIE A UN CODE peut s'appliquer soit a Bourama ET a
-- ceux qui recoivent le code ('deux', comportement actuel, valeur par
-- defaut pour tout l'existant), soit uniquement a ceux qui recoivent le
-- code ('destinataires'). Un element non lie a un code s'applique
-- toujours a son proprietaire, quelle que soit cette valeur.
alter table comportements_etudiants add column if not exists portee text not null default 'deux';
alter table comportements_etudiants drop constraint if exists comportements_etudiants_portee_valide;
alter table comportements_etudiants add constraint comportements_etudiants_portee_valide
  check (portee in ('deux', 'destinataires'));
