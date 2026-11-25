# Déblocage de palier par personne

[English version](DEBLOCAGE_PALIERS.md) · **Version française**

Ajouté le 25 novembre 2026 à la demande de Bourama. Un administrateur peut débloquer le palier d'une personne, avec ou sans date de fin. Plus tard, le webhook d'un paiement appellera la même fonction : **aucun moyen de paiement n'est branché dans cette étape.**

## Règle : Classinus n'a qu'un seul agent

Classinus n'est pas une plateforme multi-agents. Il n'y a qu'**un seul agent**. Un palier, un abonnement ou un déblocage appartient à **la personne**, jamais à un agent. Cette règle est écrite à trois endroits pour que plus personne n'ait à la redemander : le commentaire de la table `agents` dans Supabase, `CLAUDE.md` (et `CLAUDE.fr.md`), et ce document.

## Table `deblocages_paliers`

Sécurité par ligne activée et aucune règle : seul le backend (clé secrète Supabase) lit et écrit. `ON DELETE CASCADE` vers `auth.users`, et la table figure dans `core/purge_compte.py` et dans l'export des données (`api/profiles.py`).

| Colonne | Rôle |
| --- | --- |
| `user_id` | La personne qui reçoit le palier. |
| `palier` | Un nom de palier de `modeles_llm.palier` (essentiel, pro, premium, max, ultra). Aucune contrainte en base : le code le valide, donc ajouter un palier ne demande aucune migration. |
| `source` | `manuel` aujourd'hui, `paiement` quand le webhook existera. |
| `accorde_par`, `motif` | Qui l'a accordé et pourquoi (500 caractères au plus). |
| `debut`, `expire_le` | Début, et fin facultative. Sans `expire_le`, le déblocage dure jusqu'à sa révocation. |
| `revoque_le` | Rempli par une révocation. La ligne reste (historique). |

Un déblocage est **actif** quand `revoque_le` est vide et que `expire_le` est vide ou dans le futur. Le palier d'une personne est le **plus haut** de ses déblocages actifs, dans l'ordre des paliers de la configuration Supabase. Les déblocages s'ajoutent : en accorder un nouveau n'en retire aucun.

## Routes (réservées aux comptes `profiles.role = 'admin'`)

Toutes demandent un jeton de connexion. Pour désigner la personne, donner soit `user_id`, soit `email` (un seul des deux).

| Route | Ce qu'elle fait |
| --- | --- |
| `GET /api/admin/deblocages-paliers?user_id=...` ou `?email=...` | Les déblocages actifs et le plus haut palier débloqué (`palier_debloque`). |
| `POST /api/admin/deblocages-paliers` | Corps : `user_id` ou `email`, `palier`, `expire_le` (facultatif, date ISO ; sans fuseau, lue en UTC), `motif` (facultatif). Accorde le palier. |
| `POST /api/admin/deblocages-paliers/revoquer` | Corps : `user_id` ou `email`. Révoque tous les déblocages actifs de la personne. |

Les erreurs passent par des codes stables `DEBLOCAGE_*` (`core/erreurs.py`) avec un message français et un message anglais.

## Débloquer depuis le tableau de bord Supabase

Sans passer par la route, insérer une ligne dans `deblocages_paliers` : `user_id`, `palier`, et si besoin `expire_le`. Mettre `source` à `manuel` (valeur par défaut). Pour révoquer, remplir `revoque_le`.

## Désigner un administrateur

Les routes demandent `profiles.role = 'admin'` pour le compte qui appelle. Aucun compte n'a ce rôle par défaut : le donner à la main dans la table `profiles`.

## Code

- `core/deblocage_paliers.py` : toute la logique (`debloquer`, `revoquer`, `deblocages_actifs`, `palier_debloque_de`, `etat`). Le futur webhook appellera `debloquer(..., source="paiement")`.
- `api/deblocage_paliers.py` : la couche HTTP.
- `core/fournisseurs_llm.py` : `ordre_des_paliers()` donne l'ordre des paliers.
- `migrations/2026_11_25_deblocages_paliers.sql` : la table et le commentaire de la règle sur `agents`.
- `test_deblocage_paliers.py` : tests sans accès au réseau.

## Ce qui n'est PAS encore fait

- **Le palier débloqué ne change pas encore l'accès aux modèles du chat.** Aujourd'hui l'accès vient de `agents.palier_debloque` et `distributeur_debloque`, et l'unique agent est réglé sur le palier le plus haut : tout le monde voit déjà tout. Brancher le palier de la personne sur l'accès aux modèles est la prochaine étape, à décider avec Bourama (cela retire l'accès aux modèles de palier supérieur à toute personne sans déblocage).
- Les crédits mensuels des paliers ne sont pas gérés ici.
- Aucun webhook et aucun fournisseur de paiement.
- Aucun écran : l'administrateur passe par les routes ou par Supabase.

## Limites connues

- La recherche par e-mail parcourt les comptes page par page (jusqu'à 10 000 comptes). Au-delà, utiliser `user_id`.
- Une personne peut cumuler plusieurs déblocages actifs : pour raccourcir une date de fin, révoquer puis accorder à nouveau.
