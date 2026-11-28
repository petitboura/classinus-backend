# Produits publics (backend)

[English version](README.md) · **Version française**

Chantier du 28 novembre 2026, demandé par Bourama : une nouvelle section « Produits » où toute personne connectée publie son produit (un site, une appli ou une plateforme). Chaque produit a une page publique indexée par Google, avec images, nom, accroche, description, type, étiquettes et un lien.

## Décisions

- **Qui publie.** Tout compte connecté, en ligne tout de suite, sans validation préalable.
- **Modération.** Retrait après un signalement (`signalements_bibliotheque`, type `produit_public`) ou directement par un administrateur (`POST /api/produits-publics/{id}/retirer-admin`). Un produit retiré garde sa ligne (`statut = 'retire'`, motif, date) et disparaît de toutes les routes publiques (404).
- **Images.** Envoyées par le créateur et/ou capturées automatiquement depuis le site (bureau puis téléphone). Rangées dans R2, bucket `images-publiques`, dossier `produits/<id du compte>/`. Chaque image est réencodée (JPEG, ou PNG si transparente) et réduite à 1800 px de large ; un logo est recadré en carré de 512 px.
- **Nom du créateur.** Affiché seulement si le créateur a un profil public, sinon la page ne dit rien de qui l'a publié.

## Limites (toutes dans `core/config_produits_publics.py`, modifiables par variable d'environnement)

20 produits publiés par compte, 8 images par produit, 8 Mo par image envoyée, 5 étiquettes, 12 captures par heure et par compte, 2 captures en même temps sur le serveur.

## Sécurité de la capture

Le navigateur sans fenêtre fait passer chaque requête (page, redirections, scripts, images) par `valider_url_externe` : une adresse qui vise le réseau interne est coupée. Les service workers et les WebSockets sont bloqués, les téléchargements refusés.

## Routes

`GET /api/produits-publics` (recherche `q`, `type_produit`, `etiquette`, pagination `decalage` et `limite`), `GET /api/produits-publics/{id}`, `GET /api/produits-publics/mes-produits`, `POST` (publier), `PUT /{id}`, `DELETE /{id}`, `POST /images` (multipart, option `logo`), `POST /capture`. La liste et le détail ne demandent aucun compte.

## Carte du code

- `core/produits_publics.py` : validation et toute la logique.
- `core/images_produits_publics.py` : envoi, capture, purge d'un dossier.
- `core/config_produits_publics.py` : toutes les limites.
- `api/produits_publics.py` : routes. `api/signalements.py` : nouveau type de signalement.
- `migrations/2026_11_28_produits_publics.sql` : table `produits_publics` et colonne `produit_public_id` des signalements.
- Tests : `test_produits_publics.py`.

## Suppression du compte et export

`produits_publics` est purgée avec le compte (`core/purge_compte.py`, qui efface aussi le dossier d'images dans R2) et exportée (`produits_publics` dans `api/profiles.py`). La clé étrangère est en cascade vers `auth.users`.

## État

Table appliquée sur la base de staging. Base de production : pas encore, à appliquer quand le travail passera dans `main`.
