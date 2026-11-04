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

## Outils

Les outils sont enregistrés et filtrés par les modules de registre et d’autorisation, notamment `core/registre_outils.py`, `core/mcp_tools.py` et les modules d’exécution spécialisés. Certains appels nécessitent une autorisation explicite et des garde-fous côté serveur.

## Embeddings et RAG

Deux usages de la recherche vectorielle sont distingués :

- `core/retriever.py` : récupération de contenus indexés utilisés par le moteur IA.
- `core/bibliotheque_rag.py` : recherche dans la bibliothèque personnelle de fichiers de l’utilisateur.

La vectorisation et le découpage de texte sont partagés via `core/embeddings.py`. Les migrations SQL et les fonctions RPC associées constituent une partie du contrat avec Supabase.

## Indexation

Les outils de traitement et d’indexation se trouvent principalement dans `indexers/`, `core/` et `scripts/`. Avant d’ajouter un nouvel indexeur, identifier le stockage cible, la fonction de recherche vectorielle correspondante et les règles d’accès aux documents.
