> [English version](./SKILL.md) · **Version française**

---
name: "Création de skills"
description: "Méthode officielle Classinus pour aider un utilisateur à créer ou améliorer un de ses skills : définir ce qu'il fait et quand il s'applique, écrire le SKILL.md et les fichiers annexes, puis le tester. À lire quand l'utilisateur demande de créer, écrire ou améliorer un skill."
---

# Création de skills

À utiliser quand l'utilisateur veut créer, écrire, améliorer, importer ou exporter un de ses skills.

## 1. Comment fonctionne un skill

Un skill est un dossier avec un `SKILL.md` obligatoire et des fichiers texte facultatifs (`scripts/`, `references/`, `assets/`). Seuls les fichiers texte sont pris en charge. Le prompt ne montre que le nom et la description de chaque skill (la description est coupée à 400 caractères). Quand une demande correspond à une description, le `SKILL.md` complet est lu, puis les autres fichiers seulement si le `SKILL.md` le demande. La description décide donc quand le skill est utilisé, et le corps décide de la qualité de son usage.

Les skills officiels de Classinus sont en lecture seule. Si un skill de l'utilisateur et un skill officiel couvrent le même domaine, celui de l'utilisateur gagne.

## 2. Règles de l'outil

Utilise `gerer_skill`. N'écris, ne modifie et ne supprime jamais sans demande claire et explicite de l'utilisateur. Si la demande est vague, demande d'abord ce qu'il veut. Une suppression demande confirmation. Ne montre jamais d'identifiants internes.

Actions : `lister`, `consulter`, `creer`, `modifier_infos`, `ecrire_fichier`, `remplacer_texte`, `supprimer_fichier`, `importer_zip`, `exporter_zip`, `supprimer`. L'en-tête (nom et description) du `SKILL.md` est ajouté et tenu à jour automatiquement : `creer` ne prend que le corps dans `contenu`, et `modifier_infos` est le seul moyen de changer le nom ou la description.

## 3. Méthode

1. **Comprendre.** Demande ce que fait le skill, quand il doit s'appliquer, ce que l'utilisateur fournit, à quoi le résultat doit ressembler, et deux ou trois vrais exemples. Demande ce qui se passe mal aujourd'hui sans lui. Puis appelle `lister` pour vérifier qu'un skill semblable n'existe pas déjà, officiels compris.
2. **Écrire d'abord la description.** Dis ce que fait le skill et quand l'utiliser, avec les mots que l'utilisateur dirait vraiment, y compris types de fichiers ou mots-clés. Trop large, il se déclenche sur tout, trop étroite, il ne se déclenche jamais. Exemple. Faible : « Aide pour les rapports. » Mieux : « Rédige le rapport mensuel des ventes à partir d'un tableur, au format de l'entreprise. À utiliser quand l'utilisateur parle du rapport mensuel, des chiffres de vente ou de la synthèse pour la direction. »
3. **Écrire le corps.** Court et à l'impératif : étapes dans l'ordre, décisions, résultat attendu, ce qu'il ne faut jamais faire. Explique la raison d'une règle, car une règle expliquée est mieux appliquée qu'une règle nue. Déplace les longs détails dans `references/` et dis exactement quand les lire. Ne mets dans `scripts/` que du texte déterministe.
4. **Créer.** `creer` avec le nom, la description et le corps, puis `ecrire_fichier` pour chaque fichier annexe. Dis en une phrase ce qui a été fait.
5. **Tester.** Il n'y a pas de banc d'essai automatique ici, donc teste à la main. Prends trois demandes réalistes : une typique, une délicate, et une qui ne doit pas déclencher le skill. Vérifie que la description correspond aux deux premières et pas à la troisième, et que le corps donne assez pour faire la tâche sans deviner. Propose à l'utilisateur d'essayer une vraie demande dans un nouveau message et de te dire le résultat.
6. **Améliorer.** `remplacer_texte` pour une petite correction, `ecrire_fichier` pour réécrire un fichier, `modifier_infos` pour le nom ou la description. Relis le fichier avec `consulter` après un changement.

## 4. Import et export

- `exporter_zip` produit un zip téléchargeable, un dossier par skill, pour sauvegarder ou déplacer les skills. Laisse `skill_id` vide pour les exporter tous.
- `importer_zip` ajoute d'un coup tous les skills d'un zip joint au chat. Ne les lis pas et ne les recrée pas un par un.

## 5. Pièges

- Un skill est enregistré en texte et peut être exporté ou partagé. N'y mets jamais de mots de passe, de clés ni de données personnelles.
- Ne copie pas un manuel entier dans `SKILL.md`. Garde ce que le modèle ne saurait pas ou ferait mal.
- Ne crée pas un skill pour une demande ponctuelle. Un skill sert à ce que l'utilisateur refera.
