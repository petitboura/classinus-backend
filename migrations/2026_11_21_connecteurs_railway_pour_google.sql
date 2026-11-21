/*
  21/11/2026, demande de Bourama : dans la ligne des connecteurs du tableau de /abonnements, Google (masque dans
  l'appli) est remplace par Railway (affiche dans l'appli). Francais et anglais. Idempotente.
*/
update public.textes_modeles_llm
   set texte = replace(texte, 'Notion, Google, Vercel', 'Notion, Railway, Vercel'),
       updated_at = now()
 where cle = 'attente_comp_fonctions_lignes' and texte like '%Notion, Google, Vercel%';
