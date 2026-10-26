/*
Mémoire élève, catégories libres (demande de Bourama, 26/10/2026).
Retire la contrainte qui limitait les catégories de premier niveau à
identite / scolarite / apprentissage / preferences : le modèle structure
désormais lui-même la mémoire (grandes catégories + sous-catégories),
voir core/memoire_eleve.py. Ne jamais remettre cette contrainte.
*/
alter table public.memoire_eleve drop constraint if exists memoire_eleve_categorie_check;
