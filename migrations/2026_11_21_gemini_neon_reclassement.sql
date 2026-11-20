/*
  21/11/2026, demande de Bourama (appliquee a la main sur la prod et sur le staging le meme jour).
  Gemini 4 Neon (gemini-4-neon, sorti le 18/11/2026) prend le palier max (groupe 2).
  Gemini 4 Argon descend au palier premium (groupe 3), Gemini 4 Hydrogen au palier pro (groupe 4).
  Gemini 3.5 Flash-Lite, deja masque, est range au palier essentiel (inactif) pour liberer le palier pro :
  la table n'accepte qu'un modele par fournisseur et par palier (unique distributeur + palier).
  Les paliers sont decales en cascade, de bas en haut, pour ne jamais avoir deux modeles au meme palier.
*/
update public.modeles_llm
   set palier = 'essentiel', niveau = 1, groupe = 5, actif = false, updated_at = now()
 where distributeur = 'gemini' and modele_id = 'gemini-3.5-flash-lite' and palier = 'pro';

update public.modeles_llm
   set palier = 'pro', niveau = 2, groupe = 4, updated_at = now()
 where distributeur = 'gemini' and modele_id = 'gemini-4-hydrogen' and palier = 'premium';

update public.modeles_llm
   set palier = 'premium', niveau = 3, groupe = 3, updated_at = now()
 where distributeur = 'gemini' and modele_id = 'gemini-4-argon' and palier = 'max';

insert into public.modeles_llm (distributeur, palier, niveau, modele_id, label, actif, bientot, groupe)
select 'gemini', 'max', 4, 'gemini-4-neon', 'Gemini 4 Neon', true, false, 2
 where not exists (select 1 from public.modeles_llm where distributeur = 'gemini' and modele_id = 'gemini-4-neon');
