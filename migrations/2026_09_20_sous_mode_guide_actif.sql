-- Chantier "demo + guide visuel" (voir specs-demo-decouverte.md dans
-- clovis-frontend), demande Bourama, 20/09/2026.
--
-- Etend conversation_guide_actif (migration 2026_09_16b) avec sous_mode :
-- "textuel" (comportement actuel, inchange, valeur par defaut),
-- "visuel" (guide qui utilise le canal en direct pour cliquer/montrer
-- au lieu d'expliquer par texte), "demo" (demonstration ciblee des
-- affichages / outils / canal en direct, distincte du guide).
--
-- Reste sur la MEME table et le MEME conversation_id que le guide
-- textuel existant : demo et guide visuel tournent en pratique sur la
-- conversation dediee au canal en direct (voir
-- lib/contexteCanalEnDirect.tsx cote frontend), mais rien ici n'a besoin
-- de le savoir -- conversation_guide_actif ne fait deja aucune
-- hypothese sur quelle conversation lui est passee.

ALTER TABLE public.conversation_guide_actif
    ADD COLUMN IF NOT EXISTS sous_mode text NOT NULL DEFAULT 'textuel';

ALTER TABLE public.conversation_guide_actif
    ADD CONSTRAINT conversation_guide_actif_sous_mode_valide
    CHECK (sous_mode IN ('textuel', 'visuel', 'demo'));
