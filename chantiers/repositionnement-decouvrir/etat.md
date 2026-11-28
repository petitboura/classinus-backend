# Chantier : repositionnement de Classinus, côté backend (28/11/2026)

Suite du chantier du même nom dans classinus-frontend (voir son etat.md).

## Fait (staging)
- Dans les consignes envoyées à l'IA (core/construction_system_prompt.py et core/profils_agents.py), « l'étudiant » et « l'élève » sont devenus « l'utilisateur » : réponses aux QCM, programme, et textes des 4 modes pédagogiques. Aucun comportement changé, seulement les mots. Aucun autre code ne compare ces phrases.
- Vérifié : aucune consigne ne décrit Classinus comme un assistant d'étude. Il n'y avait donc rien d'autre à reformuler sur ce point.

## Volontairement laissé tel quel
- Les noms des 4 modes (Socratique, Professeur, Tuteur, Examinateur) et le mode cours : ce sont des fonctions que l'utilisateur choisit, pas le positionnement.
- Les noms de fichiers, de tables et de variables qui contiennent « etudiant » ou « eleve » (comportements_etudiants.py, memoire_eleve.py, etc.) : les renommer casserait la base et les liens entre fichiers pour un gain nul côté public.

## Pas encore fait
- Passage de staging vers main du backend.
- Autres textes pour l'IA qui disent encore élève ou étudiant (ex. consignes de mémoire, d'avancement des notions, de signalements) : à traiter si Bourama veut aller plus loin.
