> [English version](./IA_ET_RAG.md) · **Version française**

# IA, fournisseurs et recherche documentaire

## Orchestration du chat

`core/main.py` expose le point d’entrée du moteur de conversation. L’orchestration s’appuie sur des modules spécialisés pour la construction du prompt, l’historique, le routage des outils, les appels de modèles et la persistance.

Le comportement par défaut du chat et les fournisseurs premium sont deux chemins distincts. Le détail est dans `core/main.py`, `core/fournisseurs_llm.py` et les adaptateurs associés.

## Fournisseurs

Le dépôt contient des adaptateurs pour plusieurs familles de fournisseurs, notamment Groq, Google Gemini, Anthropic Claude, OpenAI, xAI/Grok, DeepSeek et Meta. Un fournisseur n’est disponible que si sa configuration et ses identifiants sont présents et si son accès est autorisé.

Les identifiants de modèles et les libellés peuvent être configurés dans Supabase. Les catalogues et versions changent : ne pas coder en dur dans la documentation une liste de modèles comme si elle était permanente.

Variables de base relevées dans le dépôt :

- `GROQ_API_KEY`
- `GOOGLE_API_KEY`

Les fournisseurs supplémentaires utilisent leurs propres variables. Voir [RAILWAY_DEPLOY.md](./deployment/RAILWAY_DEPLOY.md) pour la liste opérationnelle recensée.

## Cache de prompt et mesure des tokens

Chaque étape d'outil renvoie au modèle tout le contexte (prompt système, outils, historique, résultats d'outils) : l'entrée est le poste de coût dominant. Les fournisseurs ne relisent depuis leur cache que le **début identique** d'une requête, facturé bien moins cher. Le premier octet qui change fait refacturer tout ce qui suit.

**Disposition du prompt** (`core/construction_system_prompt.py`, assemblage dans `core/main.py`) :

1. premier message système : la partie **stable** (plateforme, page de l'agent, skills, connexions, configuration, mémoire, modes) ;
2. l'historique de la conversation ;
3. second message système : la partie **variable** (blocs qui dépendent du message ou de l'écran, date et heure, journal des outils, note d'avancement) ;
4. la question en cours.

Tout nouveau bloc de prompt qui change d'un message à l'autre se place **après** `MARQUEUR_PARTIE_VARIABLE`, jamais avant.

**Cache par fournisseur** :

| Fournisseur | Mécanisme |
|---|---|
| Claude | marqueurs `cache_control` posés par `core/adaptateur_claude.py` (dernier outil, système, fin de l'historique, dernier message). `CLAUDE_CACHE_PROMPT=0` le coupe, `CLAUDE_CACHE_TTL=1h` allonge la durée (défaut 5 min) |
| GPT, Grok | cache automatique ; `prompt_cache_key` stable envoyé par `core/adaptateur_responses.py`. `CACHE_PROMPT_CLE=0` le coupe |
| Meta, Gemini, DeepSeek, GLM, Qwen, NVIDIA | cache automatique du fournisseur, rien à envoyer : seule la stabilité du début compte |

**Mesure** (`core/usage_llm.py`) : une ligne `[USAGE]` par appel dans les logs Railway : `entree`, `cache_lu`, `cache_ecrit`, `sortie`, `part_cache`, nombre de messages et d'outils, et trois empreintes (`empreinte_outils`, `empreinte_tete`, `empreinte_debut_historique`). Si les empreintes ne changent pas d'un appel à l'autre mais que `cache_lu` reste à 0, la cause est chez le fournisseur ; si elles changent, c'est le début de la requête qui bouge. Les appels de conclusion forcée et de relecture ne sont pas encore mesurés.

Limite connue : `demander_outils` ajoute des outils en cours de tour, ce qui change le début de la requête et force une réécriture du cache à chaque ajout.

## Outils

Les outils sont enregistrés et filtrés par les modules de registre et d’autorisation, notamment `core/registre_outils.py`, `core/mcp_tools.py` et les modules d’exécution spécialisés. Certains appels nécessitent une autorisation explicite et des garde-fous côté serveur.

## Embeddings et RAG

Deux usages de la recherche vectorielle sont distingués :

- `core/retriever.py` : récupération de contenus indexés utilisés par le moteur IA.
- `core/bibliotheque_rag.py` : recherche dans la bibliothèque personnelle de fichiers de l’utilisateur.

La vectorisation et le découpage de texte sont partagés via `core/embeddings.py`. Les migrations SQL et les fonctions RPC associées constituent une partie du contrat avec Supabase.

## Indexation

Les outils de traitement et d’indexation se trouvent principalement dans `indexers/`, `core/` et `scripts/`. Avant d’ajouter un nouvel indexeur, identifier le stockage cible, la fonction de recherche vectorielle correspondante et les règles d’accès aux documents.
