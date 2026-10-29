-- 29/10/2026, demande de Bourama : réserver un fournisseur encore marqué
-- Bientôt (Meta pour commencer) à quelques adresses e-mail, sans le rendre
-- visible aux autres utilisateurs. Voir core/fournisseurs_llm.py.
--
-- Fonctionnement : tant que fournisseurs_llm.bientot vaut true, le fournisseur
-- reste grisé pour tout le monde. Une adresse listée ici voit en plus ses
-- modèles choisissables, et le serveur les accepte pour elle seule. La clé API
-- du fournisseur (MODEL_API_KEY pour Meta) reste exigée sur le serveur.
-- Pour donner l'accès à quelqu'un : ajouter une ligne. Pour le retirer : la
-- supprimer. Un changement est vu en une minute environ.
--
-- Si cette table n'existe pas encore, le backend continue comme avant (aucun
-- accès anticipé, rien d'autre ne change). Le script peut être rejoué sans
-- risque. À lancer APRÈS 2026_10_28_modeles_meta.sql : ici rien n'impose
-- l'ordre, mais l'accès ne sert que si Meta existe dans fournisseurs_llm.
--
-- La table est lue avec la clé de service du backend. RLS activée sans aucune
-- politique : aucun accès direct depuis un navigateur.

CREATE TABLE IF NOT EXISTS public.acces_anticipe_modeles (
    distributeur text NOT NULL,
    email text NOT NULL CHECK (email = lower(btrim(email))),
    ajoute_le timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (distributeur, email)
);

ALTER TABLE public.acces_anticipe_modeles ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.acces_anticipe_modeles IS 'Adresses e-mail autorisées à utiliser un fournisseur encore marqué Bientôt (fournisseurs_llm.bientot = true). Lu par le backend (cache environ 1 minute).';
COMMENT ON COLUMN public.acces_anticipe_modeles.email IS 'Adresse e-mail du compte, en minuscules et sans espaces.';

INSERT INTO public.acces_anticipe_modeles (distributeur, email) VALUES
    ('meta', 'petitboura26@gmail.com')
ON CONFLICT (distributeur, email) DO NOTHING;
