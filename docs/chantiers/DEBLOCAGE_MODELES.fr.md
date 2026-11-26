# Déblocage d'un modèle pour tout le monde ou pour une liste d'adresses

[English version](DEBLOCAGE_MODELES.md) · **Version française**

Ajouté le 26 novembre 2026 à la demande de Bourama. Un administrateur peut ouvrir **un modèle précis** à tout le monde ou à une liste d'adresses e-mail, avec ou sans date de fin. Complète le [déblocage de palier](DEBLOCAGE_PALIERS.fr.md) : là on débloque un palier entier pour une personne, ici un seul modèle.

## Ce que fait un déblocage de modèle

Le modèle devient **choisissable** (et accepté par le chat) pour les personnes visées, même s'il est :
- au-dessus de leur palier (il n'est plus grisé avec le verrou), ou
- marqué « Bientôt », que ce soit le modèle ou son fournisseur.

Ce qui reste exigé, rien d'autre n'est contourné :
- **La clé API** du fournisseur (ou celle de Vultr / Baseten pour les modèles servis seulement par eux). Sans clé, le modèle reste fermé.
- **Le fournisseur doit être ouvert par l'agent unique** (`distributeur_debloque`).
- **Le palier `specialise` (accès anticipé) ne s'ouvre jamais** par ce moyen : il reste réservé à la table `acces_anticipe_modeles`.

Un déblocage de modèle ne donne que ce modèle : les autres modèles du même fournisseur ou du même palier restent comme avant.

## Table `deblocages_modeles`

Sécurité par ligne activée et aucune règle : seul le backend lit et écrit.

| Colonne | Rôle |
| --- | --- |
| `modele_id` | L'identifiant du modèle (`modeles_llm.modele_id`, par exemple `claude-opus-5-5`). Le code le vérifie contre la configuration, aucune contrainte en base. |
| `email` | **Vide = tout le monde**, y compris un visiteur sans compte. Sinon une adresse, en minuscules et sans espaces. On peut l'ajouter avant que la personne ait un compte. |
| `accorde_par`, `motif` | Qui l'a accordé et pourquoi (500 caractères au plus). |
| `debut`, `expire_le` | Début, et fin facultative. Sans `expire_le`, le déblocage dure jusqu'à sa révocation. |
| `revoque_le` | Rempli par une révocation. La ligne reste (historique). |

Un déblocage est **actif** quand `revoque_le` est vide et que `expire_le` est vide ou dans le futur. Les déblocages s'ajoutent : redonner un déblocage déjà actif ne crée pas de doublon.

**Délai** : le backend lit la table avec la configuration des modèles (cache d'environ une minute). Un déblocage ou une révocation prend effet en moins d'une minute.

## Routes (réservées aux comptes `profiles.role = 'admin'`)

| Route | Ce qu'elle fait |
| --- | --- |
| `GET /api/admin/deblocages-modeles` (ou `?modele_id=...`) | Les déblocages actifs, regroupés par modèle : `tous` (vrai/faux) et la liste des `adresses`. |
| `POST /api/admin/deblocages-modeles` | Corps : `modele_id`, **une seule cible** : `tous: true` OU `adresses: [...]` (200 au plus par appel), puis `expire_le` (facultatif, date ISO ; sans fuseau, lue en UTC) et `motif` (facultatif). Réponse : `ajoutes` et `deja_actifs`. |
| `POST /api/admin/deblocages-modeles/revoquer` | Corps : `modele_id` et la même cible (`tous: true` OU `adresses`). Réponse : `revoques`. |

Les erreurs passent par des codes stables `DEBLOCAGE_MODELE_*` et `DEBLOCAGE_*` (`core/erreurs.py`), en français et en anglais.

## Débloquer depuis le tableau de bord Supabase

Insérer une ligne dans `deblocages_modeles` : `modele_id`, et `email` (laisser vide pour tout le monde), plus `expire_le` si besoin. Pour révoquer, remplir `revoque_le`. Attention : en passant par Supabase, la vérification que le modèle existe et que l'adresse est bien écrite n'est pas faite (la base impose seulement des minuscules sans espaces).

## Données personnelles

La table contient des adresses e-mail. À la suppression d'un compte, les lignes de son adresse sont supprimées (`core/purge_compte.py`, `_purger_deblocages_modeles`) et elles figurent dans l'export de ses données (`api/profiles.py`). Les lignes « tout le monde » (adresse vide) ne sont liées à personne et restent.

## Code

- `core/fournisseurs_llm.py` : `_lire_deblocages_modeles` (lecture avec la configuration), `modeles_disponibles_pour_agent` (le déblocage y est appliqué), `ids_des_modeles`.
- `core/deblocage_modeles.py` : écriture et lecture de la table.
- `api/deblocage_modeles.py` : la couche HTTP.
- `migrations/2026_11_26_deblocages_modeles.sql` : la table.
- `test_deblocage_modeles.py` : tests sans accès au réseau.

## Limites connues

- Pas d'écran : l'administrateur passe par les routes ou par Supabase.
- Il n'y a aucun moyen de débloquer « tous les modèles d'un fournisseur » d'un coup : un déblocage vise un modèle.
- La liste d'accès anticipé par fournisseur (`acces_anticipe_modeles`) reste à part et n'a pas changé.
