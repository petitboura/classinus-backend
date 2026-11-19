# Liste d'attente des modèles « Bientôt »

[English version](LISTE_ATTENTE_MODELES.md) · **Version française**

Ajoutée le 16 novembre 2026 à la demande de Bourama. Une fausse porte mesure la demande réelle avant de brancher Claude, GPT et Gemini. Dans le sélecteur de modèles, ces modèles apparaissent grisés avec la mention « Bientôt ». Un clic ouvre un formulaire d'inscription à une liste d'attente payante. **Aucun paiement n'est pris**, et le formulaire le dit.

## Ce que demande le formulaire

Pour s'inscrire, la personne doit être connectée, donc l'e-mail vient du compte ; la lecture des paliers est ouverte aux visiteurs. Le formulaire demande un palier (Pro 10, Max 17 ou Ultra 20 dollars par mois, ouverts à tous), un profil (étudiant, administration ou développeur), une case de consentement, et deux champs facultatifs : le pays et le WhatsApp. Les paliers et les textes ne sont pas écrits en dur :

- Les paliers vivent dans la table `paliers_liste_attente` (prix, crédit mensuel, ordre, actif).
- Les textes du formulaire vivent dans `textes_modeles_llm`, sous des clés qui commencent par `attente_`, en français et en anglais.

## Tables

Les trois tables ont la sécurité par ligne activée et aucune règle : seul le backend (clé secrète Supabase) les lit et les écrit. Les lignes liées à un compte ont `ON DELETE CASCADE` vers `auth.users`, et figurent aussi dans `core/purge_compte.py` et dans l'export des données de `api/profiles.py`.

| Table | Rôle |
| --- | --- |
| `paliers_liste_attente` | Les paliers montrés dans le formulaire. |
| `liste_attente_modeles` | UNE seule liste d'attente : une ligne par utilisateur (décision de Bourama du 17 novembre 2026, pas une liste par modèle). `modele_id` garde le modèle cliqué à l'inscription (le modèle d'origine) et ne change plus ensuite. Unique sur `user_id`. |
| `evenements_liste_attente` | Les quatre étapes de l'entonnoir, pour les chiffres investisseurs. |

Les étapes, dans l'ordre : `selecteur_ouvert`, `modele_grise_clique`, `formulaire_ouvert`, `inscription_validee`. La dernière n'est écrite que par l'inscription elle-même, jamais par le client.

## Routes

Les routes d'écriture (`POST /api/liste-attente` et `/desinscription`) demandent un utilisateur connecté. Depuis le 18/11/2026, `GET /api/liste-attente/config` et `POST /api/liste-attente/evenement` sont ouvertes aux visiteurs sans compte, pour que la page `/abonnements` soit visible sans connexion : un visiteur reçoit les paliers et les textes avec une inscription nulle, et sa note d'étape est ignorée sans erreur (`/api/liste-attente`).

| Route | Ce qu'elle fait |
| --- | --- |
| `GET /config` | Les paliers, les textes (français et anglais) et l'inscription active de l'utilisateur (`inscription`, ou null). |
| `POST /` | Crée l'inscription de l'utilisateur, ou la met à jour s'il en a déjà une (le modèle d'origine est gardé). |
| `POST /desinscription` | Passe l'inscription de l'utilisateur en `desinscrit` et efface le numéro WhatsApp. Aucun corps nécessaire. |
| `POST /evenement` | Enregistre une étape de l'entonnoir. |

Les erreurs passent par des codes stables (`LISTE_ATTENTE_*` dans `core/erreurs.py`) avec un message français et un message anglais.

## Code

- `core/liste_attente.py` : toute la logique.
- `api/liste_attente.py` : la couche HTTP.
- `migrations/2026_11_16_liste_attente_modeles.sql` : tables, paliers et textes.
- `migrations/2026_11_17_liste_attente_unique.sql` : une ligne par utilisateur, noms des paliers (Pro, Max, Ultra), points des paliers et textes réécrits pour une liste unique.
- `test_liste_attente.py` : tests sans accès au réseau.

## Groupes de modèles, verrou et badge Max

Ajouté le 17 novembre 2026 à la demande de Bourama. Le mot « Bientôt » n'existe plus dans le sélecteur : un modèle à crédit montre un **verrou**, et les modèles frontière (groupe 1) portent en plus un badge **Max**.

- `modeles_llm.groupe` (1 à 5) : 1 frontière, 2 à 4 autres modèles à crédit, 5 très bon marché et hors crédit. Il est lu à part dans `core/fournisseurs_llm.py` : une colonne absente ne casse rien (pas de groupe, pas de badge). Muse Spark Open n'a pas encore de groupe.
- Les deux listes de modèles (`modeles_disponibles_pour_agent`, `modeles_bientot_pour_agent`) envoient `groupe` et `libelles_badge` (le badge par langue, lu dans les textes `badge_groupe_<n>`).
- Le texte de la clé `bientot` dit maintenant « Disponible avec un abonnement » : c'est seulement l'info-bulle et le nom accessible du verrou.
- Placements à confirmer : Muse Spark 1.3, GPT-6 Luna, Gemini 4 Hydrogen et Grok 4.3. Migration : `migrations/2026_11_17_groupe_modeles.sql`.

## Lire les chiffres

Bourama lit les données dans le tableau de bord Supabase (la clé du backend contourne la sécurité par ligne). Le chiffre le plus convaincant est le taux de conversion à chaque étape, ventilé par modèle cliqué, palier choisi, profil et pays.

## Limites connues

- L'identifiant du modèle n'est pas vérifié par rapport au catalogue : une personne connectée pourrait envoyer un nom de modèle inconnu. Cela ne crée qu'une ligne à son nom.
- Les 30 adresses de `acces_anticipe_modeles` voient déjà les modèles : elles n'ont jamais de modèle grisé et n'atteignent jamais le formulaire.
- Une vérification juridique reste à faire avant un lancement public, car les règles varient selon les pays.
