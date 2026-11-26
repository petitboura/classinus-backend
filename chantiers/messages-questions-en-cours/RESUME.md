# Messages et questions pendant que Classinus travaille (chat)

État au 26 novembre 2026 : code fait, testé en local, poussé sur la branche `chantier-messages-questions-chat` des deux dépôts. Pas encore déployé.

## Fait
- Backend (commit f3cb004) : file de messages du tour, outil `poser_question` (bloquant ou non), routes `POST /api/chat/message-en-cours` et `POST /api/chat/question-reponse`, délai configurable (`parametres_outils`, 600 s par défaut, plafond 840 s), consigne, migration SQL, tests, docs.
- Frontend : barre de saisie utilisable pendant la génération, bulle « Pris en compte », carte de question en direct, repli en message normal, textes FR et EN, FAQ `/decouvrir/usages`, docs.

## Reste à faire (toi)
1. Appliquer `migrations/2026_11_25_questions_en_cours_chat.sql` sur staging (`prchrczmcoqngesbzzfi`), tester, puis sur la prod.
2. Redéployer ou redémarrer le service Railway (cache de 24 h).
3. Tester sur staging : message pendant un tour, question non bloquante, question bloquante (réponse, délai dépassé, bouton Arrêter, rechargement de la page).
4. Confirmer la limite Railway de 15 minutes (non vérifiée dans la doc) ; le plafond se règle par `QUESTION_DELAI_MAX_SECONDES`.

## Limites connues
- Les messages envoyés pendant un tour ne sont pas gardés comme messages à part : après rechargement ils ne s'affichent plus.
- Un message avec fichier ou localisation ne rejoint pas un tour en cours.
- Frontend non lancé dans un navigateur ici (types et contrôles seulement).
