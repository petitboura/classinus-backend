"""Tests hors ligne de l'affichage progressif des images et des vidéos (page bambara, 22/11/2026).

Aucune requête réseau : les sources de recherche et le petit LLM de tri sont remplacés par de faux.
"""
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault(
    "SUPABASE_SECRET",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x",
)

import json

from core import execution_outils, medias_progressifs as mp, recherche_image
from core.outils_page_bambara import filtrer_catalogue_par_client


def _image(numero, domaine="exemple.org"):
    return {
        "titre": f"Image {numero}",
        "url": f"https://{domaine}/photos/{numero}.jpg",
        "miniature": f"https://{domaine}/photos/{numero}_m.jpg",
        "credit": "Auteur",
        "source_domain": domaine,
    }


def _video(numero):
    return {
        "titre": f"Vidéo {numero}",
        "url": f"https://www.youtube.com/watch?v={numero:011d}",
        "chaine": "Chaîne",
        "duree": "3:10",
    }


def _garder_tout(requete, lot, genre):
    return list(range(1, len(lot) + 1))


class TestLireNumeros(unittest.TestCase):
    def test_json_valide_avec_texte_autour(self):
        self.assertEqual(mp._lire_numeros('Voici : {"gardes": [2, 1]} merci', 3), [2, 1])

    def test_numeros_hors_limites_doublons_et_texte_ignores(self):
        self.assertEqual(mp._lire_numeros('{"gardes": [0, 1, 1, 9, "2", "x"]}', 3), [1, 2])

    def test_aucun_garde_est_une_reponse_valide(self):
        self.assertEqual(mp._lire_numeros('{"gardes": []}', 3), [])

    def test_reponse_illisible_donne_none(self):
        for texte in ("", "rien", "{pas du json}", '{"autre": [1]}', None, 12):
            self.assertIsNone(mp._lire_numeros(texte, 3), texte)


class TestImagesProgressives(unittest.TestCase):
    def setUp(self):
        self.canal = mp.CanalMedias()

    def _lancer(self, sources, numeros_gardes=_garder_tout, arguments=None):
        with mock.patch.object(recherche_image, "sources_disponibles", return_value=sources), \
                mock.patch.object(mp, "_demander_numeros", side_effect=numeros_gardes):
            return mp.executer(
                "rechercher_image", arguments or {"requete": "baobab"}, self.canal, "appel1"
            )

    def test_un_bloc_par_source_envoye_avant_la_fin_de_la_recherche(self):
        """La source rapide est à l'écran pendant que la lente travaille encore."""
        lente_peut_finir = threading.Event()
        vu_avant_la_fin = []

        def rapide(requete, nombre, cle, page):
            return [_image(1), _image(2)]

        def lente(requete, nombre, cle, page):
            # Attend que le bloc de la source rapide soit déjà dans le canal.
            for _ in range(100):
                vu_avant_la_fin.extend(self.canal.vider())
                if vu_avant_la_fin:
                    break
                time.sleep(0.02)
            lente_peut_finir.set()
            return [_image(3)]

        sources = [("Rapide", rapide, None), ("Lente", lente, None)]
        resultat = self._lancer(sources)
        self.assertTrue(lente_peut_finir.is_set())
        self.assertEqual(len(vu_avant_la_fin), 1)
        self.assertEqual(vu_avant_la_fin[0]["source"], "Rapide")
        self.assertEqual(vu_avant_la_fin[0]["type"], "bloc_media")
        self.assertEqual(vu_avant_la_fin[0]["genre"], "images")
        self.assertEqual(vu_avant_la_fin[0]["id_appel"], "appel1")
        self.assertEqual(len(vu_avant_la_fin[0]["images"]), 2)
        reste = self.canal.vider()
        self.assertEqual([b["source"] for b in reste], ["Lente"])
        donnees = json.loads(resultat)
        self.assertEqual(donnees["affichees"], 3)

    def test_une_image_deja_affichee_par_une_autre_source_n_est_pas_reenvoyee(self):
        def source_a(requete, nombre, cle, page):
            return [_image(1)]

        def source_b(requete, nombre, cle, page):
            time.sleep(0.05)
            # Même image, autre paramètre d'adresse : doublon.
            doublon = dict(_image(1))
            doublon["url"] = doublon["url"] + "?utm=autre"
            return [doublon, _image(2)]

        self._lancer([("A", source_a, None), ("B", source_b, None)])
        blocs = self.canal.vider()
        toutes = [image["url"] for bloc in blocs for image in bloc["images"]]
        self.assertEqual(len(toutes), 2)
        self.assertEqual(len(set(toutes)), 2)

    def test_le_tri_ne_garde_que_les_numeros_choisis(self):
        def sources(requete, nombre, cle, page):
            return [_image(1), _image(2), _image(3)]

        resultat = self._lancer([("A", sources, None)], numeros_gardes=lambda r, lot, g: [3])
        blocs = self.canal.vider()
        self.assertEqual([i["titre"] for i in blocs[0]["images"]], ["Image 3"])
        self.assertEqual(json.loads(resultat)["affichees"], 1)

    def test_aucun_garde_n_envoie_aucun_bloc(self):
        resultat = self._lancer(
            [("A", lambda *a: [_image(1)], None)], numeros_gardes=lambda r, lot, g: []
        )
        self.assertEqual(self.canal.vider(), [])
        self.assertIn("rien n'est affiché", json.loads(resultat)["note"])

    def test_tri_en_echec_laisse_les_images_au_modele_principal(self):
        def en_panne(requete, lot, genre):
            raise TimeoutError("délai dépassé")

        resultat = self._lancer([("A", lambda *a: [_image(1), _image(2)], None)], numeros_gardes=en_panne)
        self.assertEqual(self.canal.vider(), [])
        donnees = json.loads(resultat)
        self.assertEqual(donnees["affichees"], 0)
        self.assertEqual(len(donnees["images_trouvees"]), 2)
        self.assertIn("PAS affichés", donnees["note"])

    def test_reponse_de_tri_illisible_laisse_aussi_les_images_au_modele(self):
        resultat = self._lancer(
            [("A", lambda *a: [_image(1)], None)], numeros_gardes=lambda r, lot, g: None
        )
        self.assertEqual(len(json.loads(resultat)["images_trouvees"]), 1)

    def test_une_source_en_erreur_ne_bloque_pas_les_autres(self):
        def cassee(requete, nombre, cle, page):
            raise RuntimeError("clé refusée")

        resultat = self._lancer([("Cassee", cassee, None), ("Bonne", lambda *a: [_image(1)], None)])
        self.assertEqual([b["source"] for b in self.canal.vider()], ["Bonne"])
        self.assertEqual(json.loads(resultat)["affichees"], 1)

    def test_rien_trouve_donne_le_meme_message_que_la_recherche_complete(self):
        resultat = self._lancer([("A", lambda *a: [], None)])
        self.assertEqual(resultat, "Aucune image trouvée pour cette recherche.")
        self.assertEqual(self.canal.vider(), [])

    def test_aucune_source_disponible(self):
        self.assertEqual(self._lancer([]), "Aucune image trouvée pour cette recherche.")

    def test_le_maximum_d_images_affichees_est_respecte(self):
        with mock.patch.dict(os.environ, {"MEDIAS_PROGRESSIFS_MAX_IMAGES": "3"}):
            resultat = self._lancer([("A", lambda *a: [_image(i) for i in range(1, 9)], None)])
        affichees = [i for bloc in self.canal.vider() for i in bloc["images"]]
        self.assertEqual(len(affichees), 3)
        self.assertEqual(json.loads(resultat)["affichees"], 3)

    def test_requete_vide(self):
        self.assertIn("Erreur", mp.executer("rechercher_image", {"requete": "  "}, self.canal, "a"))
        self.assertIn("Erreur", mp.executer("rechercher_image", {}, self.canal, "a"))

    def test_apres_la_fin_un_fil_en_retard_n_emet_plus_rien(self):
        """Une source qui répond après l'échéance ne dépose rien dans un canal déjà vidé."""
        liberer = threading.Event()

        def trop_lente(requete, nombre, cle, page):
            liberer.wait(5)
            return [_image(9)]

        with mock.patch.dict(os.environ, {"MEDIAS_PROGRESSIFS_DELAI_SECONDES": "1"}):
            debut = time.monotonic()
            self._lancer([("Lente", trop_lente, None), ("Vite", lambda *a: [_image(1)], None)])
            duree = time.monotonic() - debut
        self.assertLess(duree, 3)
        liberer.set()
        time.sleep(0.3)
        sources = [b["source"] for b in self.canal.vider()]
        self.assertEqual(sources, ["Vite"])


class TestPageEtNombre(unittest.TestCase):
    """`page` et `nombre` gardent le sens qu'ils ont dans rechercher_image et rechercher_video."""

    def setUp(self):
        self.canal = mp.CanalMedias()

    def _images(self, arguments, nombre_images=8):
        appels = []

        def source(requete, nombre, cle, page):
            appels.append((nombre, page))
            return [_image(i) for i in range(1, nombre_images + 1)]

        with mock.patch.object(recherche_image, "sources_disponibles", return_value=[("A", source, None)]), \
                mock.patch.object(mp, "_demander_numeros", side_effect=_garder_tout):
            resultat = mp.executer("rechercher_image", dict(arguments, requete="baobab"), self.canal, "p")
        return appels, json.loads(resultat)

    def test_la_page_demandee_est_transmise_aux_sources(self):
        appels, resume = self._images({"page": 3})
        self.assertEqual([page for _, page in appels], [3])
        self.assertEqual(resume["page"], 3)
        self.assertEqual(resume["page_suivante_suggeree"], 4)

    def test_sans_page_c_est_la_page_un(self):
        appels, resume = self._images({})
        self.assertEqual([page for _, page in appels], [1])
        self.assertEqual((resume["page"], resume["page_suivante_suggeree"]), (1, 2))

    def test_nombre_plafonne_ce_qui_est_affiche(self):
        _, resume = self._images({"nombre": 5})
        self.assertEqual(resume["affichees"], 5)
        self.assertEqual(sum(len(b["images"]) for b in self.canal.vider()), 5)

    def test_nombre_ne_depasse_jamais_le_reglage(self):
        with mock.patch.dict(os.environ, {"MEDIAS_PROGRESSIFS_MAX_IMAGES": "4"}):
            _, resume = self._images({"nombre": 100})
        self.assertEqual(resume["affichees"], 4)

    def test_valeurs_invalides_retombent_sur_les_defauts(self):
        for arguments in ({"page": "x", "nombre": "y"}, {"page": 0, "nombre": 0}, {"page": -4}, {"page": True}, {"nombre": None}):
            appels, resume = self._images(arguments)
            self.assertEqual(appels[0][1], 1, arguments)
            self.assertGreaterEqual(resume["affichees"], 1, arguments)

    def test_videos_page_et_nombre_vont_a_la_recherche(self):
        recus = {}

        def fausse_recherche(requete, nombre, page, sur_lot=None):
            recus.update(nombre=nombre, page=page)
            return []

        with mock.patch.object(mp.recherche_video, "rechercher_videos", side_effect=fausse_recherche):
            mp.executer("rechercher_video", {"requete": "x", "page": 2, "nombre": 12}, self.canal, "v")
        self.assertEqual(recus, {"nombre": 12, "page": 2})
        with mock.patch.object(mp.recherche_video, "rechercher_videos", side_effect=fausse_recherche):
            mp.executer("rechercher_video", {"requete": "x"}, self.canal, "v")
        self.assertEqual(recus, {"nombre": 30, "page": 1})


class TestVideosProgressives(unittest.TestCase):
    def test_chaque_source_de_videos_envoie_son_bloc(self):
        canal = mp.CanalMedias()

        def fausse_recherche(requete, nombre, page, sur_lot=None):
            sur_lot("YouTube", [_video(1), _video(2)])
            sur_lot("Serper", [_video(3)])
            return []

        with mock.patch.object(mp.recherche_video, "rechercher_videos", side_effect=fausse_recherche), \
                mock.patch.object(mp, "_demander_numeros", side_effect=_garder_tout):
            resultat = mp.executer("rechercher_video", {"requete": "baobab"}, canal, "v1")
        blocs = canal.vider()
        self.assertEqual(sorted(b["source"] for b in blocs), ["Serper", "YouTube"])
        self.assertTrue(all(b["genre"] == "videos" and "videos" in b for b in blocs))
        self.assertEqual(json.loads(resultat)["affichees"], 3)

    def test_rien_trouve(self):
        canal = mp.CanalMedias()
        with mock.patch.object(mp.recherche_video, "rechercher_videos", return_value=[]):
            self.assertEqual(
                mp.executer("rechercher_video", {"requete": "x"}, canal, "v"),
                "Aucune vidéo trouvée pour cette recherche.",
            )


class TestBranchement(unittest.TestCase):
    def _catalogue(self):
        noms = ["rechercher_image", "rechercher_video", "tavily_search"]
        outils = [{"type": "function", "function": {"name": n}} for n in noms]
        return outils, {n: {"url": "http://x"} for n in noms}

    def test_seule_la_page_bambara_marque_les_routes(self):
        outils, table = self._catalogue()
        _, table_page = filtrer_catalogue_par_client(outils, table, "page_bambara")
        cle = mp.CLE_ROUTE_PROGRESSIVE
        self.assertTrue(table_page["rechercher_image"][cle])
        self.assertTrue(table_page["rechercher_video"][cle])
        self.assertNotIn(cle, table_page["tavily_search"])
        # La table d'origine n'est pas modifiée.
        self.assertNotIn(cle, table["rechercher_image"])

    def test_les_autres_clients_gardent_leurs_routes_telles_quelles(self):
        for client in (None, "", "voix_bambara", "thonny", "web"):
            outils, table = self._catalogue()
            _, table_client = filtrer_catalogue_par_client(outils, table, client)
            self.assertNotIn(mp.CLE_ROUTE_PROGRESSIVE, table_client["rechercher_image"], client)

    def test_executer_un_appel_sans_marque_passe_par_le_client_mcp(self):
        appel = {"id": "a1", "name": "rechercher_image", "arguments": '{"requete": "x"}'}
        with mock.patch.object(execution_outils, "appeler_outil", return_value="via mcp") as mcp_appel, \
                mock.patch.object(mp, "executer") as progressif:
            sortie = execution_outils._executer_un_appel(appel, {"rechercher_image": {"url": "http://x"}}, None, mp.CanalMedias())
        self.assertEqual(sortie, "via mcp")
        mcp_appel.assert_called_once()
        progressif.assert_not_called()

    def test_executer_un_appel_marque_passe_par_l_affichage_progressif(self):
        appel = {"id": "a1", "name": "rechercher_image", "arguments": '{"requete": "x"}'}
        table = {"rechercher_image": {"url": "http://x", mp.CLE_ROUTE_PROGRESSIVE: True}}
        canal = mp.CanalMedias()
        with mock.patch.object(execution_outils, "appeler_outil") as mcp_appel, \
                mock.patch.object(mp, "executer", return_value="progressif") as progressif:
            sortie = execution_outils._executer_un_appel(appel, table, None, canal)
        self.assertEqual(sortie, "progressif")
        mcp_appel.assert_not_called()
        progressif.assert_called_once_with("rechercher_image", {"requete": "x"}, canal, "a1", arret=None)

    def test_attendre_termines_rend_les_blocs_avant_les_appels_termines(self):
        import concurrent.futures

        canal = mp.CanalMedias()

        def travail():
            canal.emettre({"type": "bloc_media", "id_appel": "a"})
            return "fini"

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(travail)
            ordre = list(execution_outils._attendre_termines({future: None}, None, canal))
        self.assertIsInstance(ordre[0], dict)
        self.assertIs(ordre[-1], future)

    def test_attendre_termines_sans_canal_ne_change_pas(self):
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: 1)
            self.assertEqual(list(execution_outils._attendre_termines({future: None}, None)), [future])


class TestChaineComplete(unittest.TestCase):
    """_traiter_appels de bout en bout : ordre des événements et message d'outil rendu au modèle."""

    def _appel(self):
        return {"id": "c1", "name": "rechercher_image", "arguments": json.dumps({"requete": "baobab"})}

    def test_les_blocs_arrivent_avant_le_resultat_de_l_outil(self):
        table = {"rechercher_image": {"url": "http://x", mp.CLE_ROUTE_PROGRESSIVE: True}}
        sources = [("A", lambda *a: [_image(1)], None), ("B", lambda *a: [_image(2), _image(3)], None)]
        messages = []
        with mock.patch.object(recherche_image, "sources_disponibles", return_value=sources), \
                mock.patch.object(mp, "_demander_numeros", side_effect=_garder_tout), \
                mock.patch.object(execution_outils, "appeler_outil") as mcp_appel:
            evenements = list(execution_outils._traiter_appels([self._appel()], messages, table))
        mcp_appel.assert_not_called()
        types = [e["type"] for e in evenements]
        self.assertEqual(types[0], "statut")
        self.assertEqual(types.count("bloc_media"), 2)
        dernier_bloc = max(i for i, t in enumerate(types) if t == "bloc_media")
        self.assertLess(dernier_bloc, types.index("outil_resultat"))
        self.assertLess(dernier_bloc, types.index("statut_termine"))
        # Aucun affichage automatique en double : ni "images" ni "fichiers_generes" pour ces résultats.
        self.assertNotIn("images", types)
        self.assertNotIn("fichiers_generes", types)
        # Le modèle principal reçoit le résumé, rattaché au bon appel.
        self.assertEqual(messages[-1]["role"], "tool")
        self.assertEqual(messages[-1]["tool_call_id"], "c1")
        resume = json.loads(messages[-1]["content"])
        self.assertEqual(resume["affichees"], 3)
        self.assertNotIn("images_trouvees", resume)
        self.assertNotIn("http", messages[-1]["content"])

    def test_sans_marque_le_chemin_d_avant_est_intact(self):
        table = {"rechercher_image": {"url": "http://x"}}
        messages = []
        sortie_mcp = json.dumps({"images_trouvees": [{"titre": "t", "url": "https://x.org/t.jpg"}]})
        with mock.patch.object(execution_outils, "appeler_outil", return_value=sortie_mcp) as mcp_appel, \
                mock.patch.object(mp, "executer") as progressif:
            evenements = list(execution_outils._traiter_appels([self._appel()], messages, table))
        mcp_appel.assert_called_once()
        progressif.assert_not_called()
        self.assertNotIn("bloc_media", [e["type"] for e in evenements])
        self.assertEqual(messages[-1]["tool_call_id"], "c1")


if __name__ == "__main__":
    unittest.main()
