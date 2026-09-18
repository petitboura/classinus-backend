-- Chantier profil contributeur / analytique bibliothèque publique (demande
-- Bourama, 18/09/2026, étape 1).
--
-- Ajoute le réglage "profil public" : bio, nom et photo ne sont visibles
-- par un visiteur externe (via GET /api/profiles/{user_id}, voir
-- api/profiles.py) que si ce réglage est activé. Le propriétaire voit
-- toujours les siennes, quel que soit l'état du réglage.
--
-- Note : cette migration documente a posteriori un état déjà appliqué en
-- base (colonne créée via l'outil Supabase avant d'être versionnée ici),
-- pas un changement de schéma à exécuter à nouveau.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS profil_public boolean NOT NULL DEFAULT false;
