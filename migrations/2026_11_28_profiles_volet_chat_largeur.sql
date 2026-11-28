-- 28/11/2026, demande Bourama : le chat s'affiche collé à droite des pages
-- (PC) au lieu de flotter, et on l'élargit en tirant sa barre. La largeur
-- choisie est retrouvée sur n'importe quel appareil où le compte se connecte
-- (voir api/profiles.py, MettreAJourProfilPayload et ProfilPublic, et
-- components/chat/ColonneChatLateral.tsx côté frontend).
--
-- Même convention "privée" que popup_chat_x/y/largeur/hauteur : la vraie
-- valeur n'est donnée qu'au propriétaire du profil, jamais sur un profil
-- public. NULL = jamais réglée, le frontend prend sa largeur par défaut.
--
-- Déjà appliquée sur les projets Supabase Classinus et Classinus Staging.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS volet_chat_largeur integer;
