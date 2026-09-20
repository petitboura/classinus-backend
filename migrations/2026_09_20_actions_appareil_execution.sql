-- 20/09/2026 : empêcher la double exécution d'une action mobile.
-- Une action est revendiquée atomiquement avant exécution. Elle passe de
-- en_attente à en_execution et ne redevient jamais automatiquement
-- disponible : une perte réseau après l'exécution ne doit pas provoquer
-- une seconde création/suppression/déplacement sur le téléphone.
alter table actions_appareil_mobile
    drop constraint if exists actions_appareil_mobile_statut_check;

alter table actions_appareil_mobile
    add constraint actions_appareil_mobile_statut_check
    check (statut in ('en_attente', 'en_execution', 'executee', 'echouee'));

alter table actions_appareil_mobile
    add column if not exists prise_en_charge_le timestamptz;

create index if not exists idx_actions_appareil_mobile_user_attente
    on actions_appareil_mobile (user_id, statut, cree_le);
