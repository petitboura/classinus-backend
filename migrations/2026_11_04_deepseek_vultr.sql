/*
04/11/2026, demande Bourama (hackathon Vultr Agent Rush) : routage DeepSeek par Vultr
Serverless Inference (staging d'abord).
C'est le MEME DeepSeek dans le selecteur : seule la route change derriere, comme pour Baseten.
Interrupteur : colonne vultr_actif (OFF par defaut = route habituelle comme avant, Bourama seul
decide quand l'allumer). Identifiants : colonne modele_id_vultr (identifiants chez Vultr, relevés
par un vrai appel a GET https://api.vultrinference.com/v1/models le 04/11/2026, puis testes
avec scripts/sonder_vultr.py : texte, appel d'outil aller-retour, vision, niveaux d'effort).
Le backend relit cette configuration environ chaque minute ; sans ces colonnes (migration pas
encore appliquee), il se comporte comme avant.

Le palier pro (deepseek-v4-pro) n'a pas de modele equivalent chez Vultr : il reste sur sa route
habituelle. Seul deepseek-v4-flash (paliers essentiel et avance) est route vers Vultr.

Ordre de priorite quand les deux interrupteurs sont ON : Vultr d'abord ; s'il refuse (credit,
quota, cle, modele retire), la route habituelle (Baseten, puis DeepSeek direct) prend le relais
sans erreur pour l'eleve.

Le script peut etre rejoue sans risque (IF NOT EXISTS, UPDATE conditionnes).

Pour activer Vultr (quand la cle VULTR_INFERENCE_API_KEY est posee sur le serveur) :
  UPDATE public.fournisseurs_llm SET vultr_actif = true WHERE distributeur = 'deepseek';
Pour revenir a la route habituelle :
  UPDATE public.fournisseurs_llm SET vultr_actif = false WHERE distributeur = 'deepseek';
*/

ALTER TABLE public.fournisseurs_llm ADD COLUMN IF NOT EXISTS vultr_actif boolean NOT NULL DEFAULT false;
ALTER TABLE public.modeles_llm ADD COLUMN IF NOT EXISTS modele_id_vultr text;

COMMENT ON COLUMN public.fournisseurs_llm.vultr_actif IS 'true = les appels de ce fournisseur passent par Vultr Serverless Inference (cle VULTR_INFERENCE_API_KEY), avec repli auto vers la route habituelle si Vultr refuse (credit epuise). Aujourd''hui seul deepseek l''utilise. Lu par le backend (cache environ 1 minute).';
COMMENT ON COLUMN public.modeles_llm.modele_id_vultr IS 'Identifiant du modele chez Vultr, envoye a la place de modele_id quand vultr_actif vaut true. NULL = jamais servi par Vultr.';

UPDATE public.modeles_llm SET modele_id_vultr = 'deepseek-v4.1-flash-1017'
WHERE distributeur = 'deepseek' AND modele_id = 'deepseek-v4-flash' AND modele_id_vultr IS NULL;
