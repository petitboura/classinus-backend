> [English version](./DONNEES_ET_SECURITE.md) · **Version française**

# Données et sécurité

## Supabase

Le backend utilise Supabase pour l’authentification, PostgreSQL et les stockages associés. Les variables serveur centrales sont `SUPABASE_URL` et `SUPABASE_SECRET`.

`SUPABASE_SECRET` est une valeur privilégiée : elle ne doit jamais être exposée au navigateur, enregistrée dans le dépôt ou incluse dans une application mobile/desktop.

Le frontend utilise une clé publique anon séparée. Une clé publique n’est pas un substitut à l’authentification ni aux règles d’accès en base.

## Authentification

Les routes protégées utilisent les dépendances d’authentification du backend, notamment `api/auth.py`. L’identité d’un utilisateur doit être déduite du jeton validé, pas d’un identifiant libre fourni dans le corps de la requête.

Les serveurs MCP publics ont leur propre vérification de jeton et leur configuration OAuth, décrites dans [MCP et connecteurs](MCP_ET_CONNECTEURS.md).

## RLS et séparation des données

Les politiques Row Level Security (RLS), les contraintes et les fonctions SQL font partie intégrante de la sécurité des données. Elles sont définies ou modifiées par les fichiers de `migrations/`.

Avant de modifier une table ou une fonction :

1. Lire les migrations existantes qui la concernent.
2. Vérifier les politiques RLS, les clés étrangères, les contraintes et les fonctions RPC.
3. Ajouter une migration versionnée et réexécutable lorsque c’est possible.
4. Tester avec un utilisateur autorisé et un autre utilisateur qui ne doit pas accéder aux données.
5. Appliquer la migration sur l’environnement correspondant avant le déploiement qui en dépend.

Le rôle serveur privilégié ne justifie pas de supprimer les contrôles d’accès applicatifs.

## Secrets et configuration

Les secrets de fournisseurs IA, OAuth, push et stockage sont configurés dans l’environnement d’exécution backend. Les noms et usages recensés sont maintenus dans [RAILWAY_DEPLOY.md](./deployment/RAILWAY_DEPLOY.md).

Ne jamais committer des secrets réels, envoyer une clé privée dans une variable frontend `NEXT_PUBLIC_*`, retourner un jeton d’intégration au client après l’avoir stocké, accepter un `user_id` client comme preuve d’identité ou exposer des données d’un autre compte.

## Fichiers et stockage

Les flux de fichiers utilisent plusieurs modules selon leur origine et leur destination, notamment les uploads, les bibliothèques, les fichiers R2 et les relais de fichiers externes. Vérifier les permissions de lecture/écriture et le propriétaire du fichier à chaque ajout de route ou d’outil.
