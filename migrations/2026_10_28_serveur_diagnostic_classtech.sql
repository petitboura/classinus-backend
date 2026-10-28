-- Serveur diagnostic Class-Tech (28/10/2026, demande Bourama) : déclare le
-- serveur MCP diagnostic_classtech comme disponible côté plateforme, même
-- mécanisme que serveur_google_drive (catégorie 2 = sans utilisateur
-- connecté : le serveur est public, lecture libre, écritures confirmées
-- via OUTILS_SENSIBLES). Sans cette ligne, le serveur existe dans le code
-- (core/registre_outils.py) mais core/mcp_tools.py::_serveurs_disponibles()
-- ne le retient jamais.
-- L'URL exacte (https://class-tech-outils.onrender.com/mcp/diagnostic) sera
-- vérifiée après création du service Render ; ajuster _url_builder si besoin.

insert into registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values ('serveur_diagnostic_classtech', 2, 'diagnostic_classtech', true, now())
on conflict (nom_outil) do update set disponible = true, updated_at = now();
