/*
04/11/2026, demande Bourama : trois nouveaux fournisseurs du selecteur, tous servis par Vultr
Serverless Inference avec UNE seule cle (VULTR_INFERENCE_API_KEY) : Z.ai (GLM), Alibaba (Qwen) et
NVIDIA (Nemotron). A appliquer APRES 2026_11_04_meta_glimmer.sql (qui ajoute la colonne vultr_seul).

Ils ne sont pas en Bientot : des que la cle Vultr existe sur le serveur, ils apparaissent ; sans la cle,
ils disparaissent tous les trois ensemble (meme regle de cle que les autres fournisseurs).
Le palier pro reste vide partout, volontairement : on ne gonfle pas un palier pour le remplir.

Ordre d'affichage (colonne ordre, unique) : zai 7, alibaba 8, nvidia 9.

Identifiants chez Vultr (modele_id_vultr) : releves dans le catalogue public des modeles Vultr
le 04/11/2026 ; le backend les confronte au vrai GET /v1/models a chaque appel (cache 10 minutes), donc
un suffixe de date ajoute par Vultr est retrouve tout seul. A re-sonder avec scripts/sonder_vultr.py.

Rejouable sans risque (ON CONFLICT).
*/

INSERT INTO public.fournisseurs_llm (distributeur, ordre, bientot, cle_api_requise, variable_cle_api, nom_affiche, baseten_actif, vultr_actif)
VALUES
  ('zai',     7, false, true, 'VULTR_INFERENCE_API_KEY', 'Z.ai',    false, true),
  ('alibaba', 8, false, true, 'VULTR_INFERENCE_API_KEY', 'Alibaba', false, true),
  ('nvidia',  9, false, true, 'VULTR_INFERENCE_API_KEY', 'NVIDIA',  false, true)
ON CONFLICT (distributeur) DO UPDATE
SET ordre = EXCLUDED.ordre, bientot = false, cle_api_requise = true,
    variable_cle_api = EXCLUDED.variable_cle_api, nom_affiche = EXCLUDED.nom_affiche,
    vultr_actif = true, updated_at = now();

INSERT INTO public.modeles_llm (distributeur, palier, niveau, modele_id, label, actif, modele_id_vultr, vultr_seul)
VALUES
  ('zai',     'essentiel', 1, 'glm-5.3-flash',                         'GLM 5.3 Flash',        true, 'glm-5.3-flash',                           true),
  ('zai',     'avance',    3, 'glm-5.3',                               'GLM 5.3',              true, 'glm-5.3',                                 true),
  ('alibaba', 'essentiel', 1, 'qwen3.8-flash-next',                    'Qwen 3.8 Flash Next',  true, 'qwen3.8-flash-next',                      true),
  ('alibaba', 'avance',    3, 'qwen3.8-27b',                           'Qwen 3.8 27B',         true, 'qwen3.8-27b',                             true),
  ('nvidia',  'essentiel', 1, 'nemotron-nano-omni-30b-a3b-reasoning',  'Nemotron Nano Omni 30B', true, 'nemotron-3-nano-omni-30b-a3b-reasoning', true)
ON CONFLICT (distributeur, palier) DO UPDATE
SET niveau = EXCLUDED.niveau, modele_id = EXCLUDED.modele_id, label = EXCLUDED.label, actif = true,
    modele_id_vultr = EXCLUDED.modele_id_vultr, vultr_seul = true, updated_at = now();
