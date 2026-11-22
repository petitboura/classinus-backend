"""Tests des phrases proactives de la page bambara (22/11/2026).

Règles verrouillées : l'audio d'une phrase n'est proposé que s'il a été fabriqué avec la voix ET le texte
actuels (changer l'un des deux le rend à refaire) ; une phrase qui échoue n'arrête pas les autres et n'est
pas retentée tout de suite ; un texte changé pendant la fabrication n'écrit rien ; les délais ont des
valeurs de secours ; chaque erreur a son message en français et en anglais ; les moments de la base et du
code sont les mêmes. Aucun réseau ni base : un faux client Supabase en mémoire suffit.
"""
import base64
import io
import re
import sys
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core import phrases_bambara as pb
from core.bambara_profils import ErreurBambara
from core.erreurs import MESSAGES_EN, MESSAGES_FR

RACINE = Path(__file__).parent
ID_1 = "11111111-1111-4111-8111-111111111111"
ID_2 = "22222222-2222-4222-8222-222222222222"
ID_3 = "33333333-3333-4333-8333-333333333333"


def wav(secondes: float = 1.0, cadence: int = 8000) -> bytes:
    sortie = io.BytesIO()
    with wave.open(sortie, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(cadence)
        f.writeframes(b"\x00\x00" * int(cadence * secondes))
    return sortie.getvalue()


class _Reponse:
    def __init__(self, data):
        self.data = data


class _Requete:
    def __init__(self, base, nom):
        self.base, self.nom = base, nom
        self.action = "select"
        self.filtres = []
        self.champs = None
        self.limite = None
        self.valeurs = None

    def select(self, champs="*"):
        self.action = "select"
        self.champs = None if champs == "*" else [c.strip() for c in champs.split(",")]
        return self

    def update(self, valeurs):
        self.action, self.valeurs = "update", dict(valeurs)
        return self

    def eq(self, colonne, valeur):
        self.filtres.append((colonne, valeur))
        return self

    def limit(self, n):
        self.limite = n
        return self

    def execute(self):
        if self.base.panne:
            raise RuntimeError("base indisponible")
        table = self.base.tables.setdefault(self.nom, [])
        gardees = [l for l in table if all(l.get(c) == v for c, v in self.filtres)]
        if self.action == "update":
            for ligne in gardees:
                ligne.update(self.valeurs)
            return _Reponse([dict(l) for l in gardees])
        if self.limite is not None:
            gardees = gardees[: self.limite]
        if self.champs:
            gardees = [{c: l.get(c) for c in self.champs} for l in gardees]
        return _Reponse([dict(l) for l in gardees])


class FauxClient:
    def __init__(self):
        self.tables = {pb.TABLE_PHRASES: [], pb.TABLE_REGLAGES: []}
        self.panne = False

    def table(self, nom):
        return _Requete(self, nom)

    def phrase(self, identifiant, moment="accueil", texte="Texte", actif=True, voix=None, audio=None):
        ligne = {"id": identifiant, "moment": moment, "texte": texte, "actif": actif,
                 "audio_base64": None, "audio_duree_ms": None, "audio_empreinte": None}
        if voix is not None:
            contenu = audio or wav()
            ligne.update(audio_base64=base64.b64encode(contenu).decode(), audio_duree_ms=1000,
                         audio_empreinte=pb.empreinte(voix, texte))
        self.tables[pb.TABLE_PHRASES].append(ligne)
        return ligne

    def ligne(self, identifiant):
        return next(l for l in self.tables[pb.TABLE_PHRASES] if l["id"] == identifiant)


class TestsPhrasesBambara(unittest.TestCase):
    def setUp(self):
        pb._en_fabrication.clear()
        pb._derniers_echecs.clear()
        self.client = FauxClient()

    # Empreinte
    def test_empreinte_change_avec_la_voix_et_avec_le_texte(self):
        base = pb.empreinte("gemini_tts", "A")
        self.assertEqual(base, pb.empreinte("gemini_tts", "A"))
        self.assertNotEqual(base, pb.empreinte("elevenlabs_tts", "A"))
        self.assertNotEqual(base, pb.empreinte("gemini_tts", "B"))

    # Liste
    def test_liste_separe_les_phrases_pretes_de_celles_a_fabriquer(self):
        self.client.phrase(ID_1, "accueil", "A", voix="gemini_tts")
        self.client.phrase(ID_2, "recherche_web", "B")
        reponse, a_fabriquer = pb.lister_phrases(self.client, "gemini_tts")
        self.assertEqual([p["id"] for p in reponse["phrases"]], [ID_1])
        self.assertEqual(a_fabriquer, [ID_2])
        self.assertEqual(reponse["en_preparation"], 1)
        self.assertEqual(reponse["phrases"][0]["duree_ms"], 1000)
        self.assertEqual(reponse["phrases"][0]["version"], pb.empreinte("gemini_tts", "A"))
        self.assertNotIn("audio_base64", reponse["phrases"][0])

    def test_changer_la_voix_remet_toutes_les_phrases_a_fabriquer(self):
        self.client.phrase(ID_1, "accueil", "A", voix="gemini_tts")
        reponse, a_fabriquer = pb.lister_phrases(self.client, "elevenlabs_tts")
        self.assertEqual(reponse["phrases"], [])
        self.assertEqual(a_fabriquer, [ID_1])

    def test_phrases_inactives_ou_de_moment_inconnu_sont_ignorees(self):
        self.client.phrase(ID_1, "accueil", "A", actif=False)
        self.client.phrase(ID_2, "moment_invente", "B", voix="gemini_tts")
        self.client.phrase(ID_3, "accueil", "   ", voix="gemini_tts")
        reponse, a_fabriquer = pb.lister_phrases(self.client, "gemini_tts")
        self.assertEqual(reponse["phrases"], [])
        self.assertEqual(a_fabriquer, [])

    def test_liste_sans_phrase_rend_des_listes_vides(self):
        reponse, a_fabriquer = pb.lister_phrases(self.client, "gemini_tts")
        self.assertEqual(reponse["phrases"], [])
        self.assertEqual(reponse["en_preparation"], 0)
        self.assertEqual(a_fabriquer, [])

    def test_base_en_panne_donne_un_code_stable(self):
        self.client.panne = True
        with self.assertRaises(ErreurBambara) as e:
            pb.lister_phrases(self.client, "gemini_tts")
        self.assertEqual(e.exception.code, "BAMBARA_INDISPONIBLE")

    # Réglages
    def test_reglages_valeurs_de_secours(self):
        self.assertEqual(pb.lire_reglages(self.client), {"delai_outil_lent_s": 6, "intervalle_outil_lent_s": 12})

    def test_reglages_lus_dans_la_base(self):
        self.client.tables[pb.TABLE_REGLAGES].append({"delai_outil_lent_s": 4, "intervalle_outil_lent_s": 20})
        self.assertEqual(pb.lire_reglages(self.client), {"delai_outil_lent_s": 4, "intervalle_outil_lent_s": 20})

    def test_reglages_invalides_reviennent_aux_valeurs_de_secours(self):
        self.client.tables[pb.TABLE_REGLAGES].append({"delai_outil_lent_s": 0, "intervalle_outil_lent_s": "vite"})
        self.assertEqual(pb.lire_reglages(self.client), {"delai_outil_lent_s": 6, "intervalle_outil_lent_s": 12})

    def test_reglages_base_en_panne_ne_cassent_pas_la_liste(self):
        self.client.panne = True
        self.assertEqual(pb.lire_reglages(self.client)["delai_outil_lent_s"], 6)

    # Audio
    def test_audio_prete_rend_les_octets(self):
        contenu = wav(0.5)
        self.client.phrase(ID_1, "accueil", "A", voix="gemini_tts", audio=contenu)
        self.assertEqual(pb.lire_audio(self.client, ID_1, "gemini_tts"), contenu)

    def test_audio_introuvable_si_voix_changee_ou_pas_fabrique_ou_identifiant_faux(self):
        self.client.phrase(ID_1, "accueil", "A", voix="gemini_tts")
        self.client.phrase(ID_2, "accueil", "B")
        self.client.phrase(ID_3, "accueil", "C", actif=False, voix="gemini_tts")
        for identifiant, voix in ((ID_1, "elevenlabs_tts"), (ID_2, "gemini_tts"), (ID_3, "gemini_tts"),
                                  ("pas-un-uuid", "gemini_tts"), ("44444444-4444-4444-8444-444444444444", "gemini_tts")):
            with self.assertRaises(ErreurBambara) as e:
                pb.lire_audio(self.client, identifiant, voix)
            self.assertEqual(e.exception.code, "BAMBARA_PHRASE_INTROUVABLE", identifiant)

    def test_audio_abime_est_introuvable_et_non_une_erreur_serveur(self):
        ligne = self.client.phrase(ID_1, "accueil", "A", voix="gemini_tts")
        ligne["audio_base64"] = "%%%pas du base64%%%"
        with self.assertRaises(ErreurBambara) as e:
            pb.lire_audio(self.client, ID_1, "gemini_tts")
        self.assertEqual(e.exception.code, "BAMBARA_PHRASE_INTROUVABLE")

    # Fabrication
    def test_fabrication_garde_audio_duree_et_empreinte(self):
        self.client.phrase(ID_1, "accueil", "A")
        n = pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], lambda texte: wav(2.0))
        self.assertEqual(n, 1)
        ligne = self.client.ligne(ID_1)
        self.assertEqual(ligne["audio_duree_ms"], 2000)
        self.assertEqual(ligne["audio_empreinte"], pb.empreinte("gemini_tts", "A"))
        self.assertEqual(base64.b64decode(ligne["audio_base64"]), wav(2.0))
        self.assertEqual(pb.lire_audio(self.client, ID_1, "gemini_tts"), wav(2.0))

    def test_fabrication_envoie_le_texte_de_la_phrase_au_tts(self):
        self.client.phrase(ID_1, "accueil", "Bonjour")
        vus = []
        pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], lambda texte: vus.append(texte) or wav())
        self.assertEqual(vus, ["Bonjour"])

    def test_une_phrase_qui_echoue_n_arrete_pas_les_autres(self):
        self.client.phrase(ID_1, "accueil", "A")
        self.client.phrase(ID_2, "recherche_web", "B")

        def tts(texte):
            if texte == "A":
                raise RuntimeError("voix en panne")
            return wav()

        with self.assertLogs(level="ERROR"):
            n = pb.fabriquer_audios(self.client, "gemini_tts", [ID_1, ID_2], tts)
        self.assertEqual(n, 1)
        self.assertIsNone(self.client.ligne(ID_1)["audio_empreinte"])
        self.assertIsNotNone(self.client.ligne(ID_2)["audio_empreinte"])

    def test_une_phrase_en_echec_n_est_pas_retentee_tout_de_suite(self):
        self.client.phrase(ID_1, "accueil", "A")
        appels = []

        def tts(texte):
            appels.append(texte)
            raise RuntimeError("voix en panne")

        with self.assertLogs(level="ERROR"):
            pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], tts)
            pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], tts)
        self.assertEqual(len(appels), 1)
        pb._derniers_echecs[ID_1] -= pb.DELAI_AVANT_NOUVEL_ESSAI_S + 1
        with self.assertLogs(level="ERROR"):
            pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], tts)
        self.assertEqual(len(appels), 2)

    def test_audio_vide_compte_comme_un_echec(self):
        self.client.phrase(ID_1, "accueil", "A")
        with self.assertLogs(level="ERROR"):
            n = pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], lambda texte: b"")
        self.assertEqual(n, 0)
        self.assertIsNone(self.client.ligne(ID_1)["audio_base64"])

    def test_texte_change_pendant_la_fabrication_n_ecrit_rien(self):
        ligne = self.client.phrase(ID_1, "accueil", "A")

        def tts(texte):
            ligne["texte"] = "A modifié"
            return wav()

        n = pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], tts)
        self.assertEqual(n, 1)
        self.assertIsNone(ligne["audio_empreinte"])
        reponse, a_fabriquer = pb.lister_phrases(self.client, "gemini_tts")
        self.assertEqual(a_fabriquer, [ID_1])

    def test_phrase_deja_en_cours_est_laissee_a_l_autre_appel(self):
        self.client.phrase(ID_1, "accueil", "A")
        pb._en_fabrication.add(ID_1)
        appels = []
        n = pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], lambda t: appels.append(t) or wav())
        self.assertEqual((n, appels), (0, []))

    def test_phrase_retiree_pendant_l_attente_est_ignoree(self):
        n = pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], lambda t: wav())
        self.assertEqual(n, 0)

    def test_le_verrou_est_toujours_relache(self):
        self.client.phrase(ID_1, "accueil", "A")
        with self.assertLogs(level="ERROR"):
            pb.fabriquer_audios(self.client, "gemini_tts", [ID_1], lambda t: 1 / 0)
        self.assertEqual(pb._en_fabrication, set())

    def test_duree_wav(self):
        self.assertEqual(pb.duree_wav_ms(wav(1.5)), 1500)
        self.assertEqual(pb.duree_wav_ms(b"pas un wav"), 0)

    # Erreurs et cohérence
    def test_codes_d_erreur_ont_un_message_francais_et_anglais_sans_tiret_double(self):
        for code in ("BAMBARA_PHRASE_INTROUVABLE", "BAMBARA_INDISPONIBLE"):
            self.assertIn(code, MESSAGES_FR)
            self.assertIn(code, MESSAGES_EN)
            for texte in (MESSAGES_FR[code], MESSAGES_EN[code]):
                self.assertNotIn("--", texte)
                self.assertNotIn("—", texte)

    def test_moments_du_code_et_de_la_migration_sont_les_memes(self):
        sql = (RACINE / "migrations" / "2026_11_22_page_bambara_phrases_proactives.sql").read_text(encoding="utf-8")
        bloc = re.search(r"check \(moment in \((.*?)\)\)", sql, re.S).group(1)
        self.assertEqual(tuple(re.findall(r"'([a-z_]+)'", bloc)), pb.MOMENTS)

    def test_migration_n_a_aucune_colonne_de_compte(self):
        sql = (RACINE / "migrations" / "2026_11_22_page_bambara_phrases_proactives.sql").read_text(encoding="utf-8")
        self.assertNotRegex(sql, r"user_id|auth\.users")
        self.assertEqual(sql.count("enable row level security"), 2)

    def test_la_route_est_branchee_et_sans_donnee_de_compte(self):
        main = (RACINE / "api" / "main.py").read_text(encoding="utf-8")
        self.assertIn("bambara_phrases_router", main)
        self.assertIn("app.include_router(bambara_phrases_router)", main)
        route = (RACINE / "api" / "bambara_phrases.py").read_text(encoding="utf-8")
        self.assertIn("immutable", route)
        self.assertNotIn("utilisateur.id", route)


if __name__ == "__main__":
    unittest.main()
