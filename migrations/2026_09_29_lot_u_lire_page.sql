-- Lot U uniquement : rendre lire_page disponible pour le modèle.
-- Idempotent si l'outil a déjà été activé dans la base.
insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('lire_page', 1, 'generation', true, now())
on conflict (nom_outil) do update
set disponible = true, updated_at = now();
