/*
  Classinus : etape reelle d'une generation Higgsfield.
  'attente'  = la demande attend son tour chez Higgsfield (statut queued ou pending)
  'creation' = la video ou l'image est en cours de creation
  Ajout seul : aucune ligne existante n'est modifiee ni supprimee. Les anciennes lignes
  prennent 'attente' par defaut puis le serveur les corrige au prochain passage.
*/
alter table public.higgsfield_generations
  add column if not exists etape text not null default 'attente'
  check (etape in ('attente', 'creation'));
