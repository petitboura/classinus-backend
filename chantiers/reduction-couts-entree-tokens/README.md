# Chantier : réduire le coût d'entrée des tokens

Dernière mise à jour : 24/11/2026. Branche de travail : staging. Statut : analyse faite, rien n'est encore implémenté.

## Objectif
Faire payer le moins possible ce que l'IA relit à chaque message (consignes, outils, historique), sans jamais perdre de contexte.

## Déjà en place (constaté dans le code le 24/11)
- Claude : mise en cache des consignes, des outils et du début de la conversation (4 repères posés), relecture à prix réduit.
- GPT et Grok : clé de regroupement envoyée pour reconnaître le début identique d'un message à l'autre.
- DeepSeek et Gemini : cache automatique chez le fournisseur, déjà lu par le compteur d'usage.
- Groq, Vultr, Baseten : rien à régler côté code, la liste d'outils reste stable pendant une réponse.
- OpenRouter : sert uniquement à la vectorisation des documents, pas au chat. Rien à réduire.
- Historique : les sujets clos sont remplacés par un rappel gratuit, seuils à 40 000 puis 60 000 caractères.
- Résultats d'outils anciens : remplacés par un pointeur, récupérables à la demande.
- Outils chargés à la demande (demander_outils).

## À faire, par ordre de rentabilité
1. Mesurer en production la part réellement relue à prix réduit, modèle par modèle (le compteur d'usage l'enregistre déjà). Décide si les points suivants valent la peine.
2. Vérifier que le début des consignes envoyées reste identique d'un message à l'autre. Tout ce qui change (date, état de la conversation, matière, mémoire de l'élève) doit venir à la fin. Non vérifié à ce jour.
3. Allonger la durée du cache Claude de 5 minutes à 1 heure (réglage, coût d'écriture un peu plus élevé).
4. Le second appel de clôture des sujets en arrière-plan utilise le même gros modèle avec tout le contexte : le confier à un petit modèle.
5. Abaisser les seuils d'allègement de l'historique (par exemple 25 000 et 40 000 caractères), au prix de rappels plus fréquents.
6. Raccourcir les gros résultats de recherche web et de documents renvoyés à l'IA.

## Décisions de Bourama
Aucune décision prise encore sur les points 2 à 6. Il a demandé de commencer par 1 puis 2.

## Pour reprendre
Aucun code modifié. Commencer par la mesure (point 1), puis le contrôle de l'ordre des consignes (point 2).
