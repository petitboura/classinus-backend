/*
Mémoire élève (26/10/2026, demande de Bourama) : nouvel outil
memoire_completer, qui ajoute ou modifie un élément d'une fiche sans la
relire ni la réécrire. Même déclaration plateforme que les autres outils
mémoire (voir migrations/2026_09_27_memoire_eleve.sql), sans elle l'outil
existe dans le code mais n'est jamais proposé au modèle.
*/
insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('memoire_completer', 1, 'generation', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
