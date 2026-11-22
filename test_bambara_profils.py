"""Tests des profils, de l'historique et des éléments gardés de la page bambara (18/11/2026).

Règles verrouillées : un profil n'est jamais lu ni utilisé par un autre compte ; le premier message d'une
conversation n'est écrit qu'une fois ; un vocal invalide ou trop long est refusé ; une vidéo ou image
n'est gardée qu'une fois ; chaque erreur a son message en français et en anglais ; les tables sont dans la
purge du compte et dans l'export. Aucun réseau ni base : un faux client Supabase en mémoire suffit.
"""
import base64
import re
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.bambara_profils import (
    LONGUEUR_MAX_AUDIO_BASE64,
    MAX_PROFILS_PAR_COMPTE,
    ErreurBambara,
    creer_profil,
    enregistrer_premier_message,
    garder,
    lire_audio,
    lister_conversations,
    lister_gardes,
    lister_profils,
    normaliser_profil,
    retirer_garde,
)
from core.erreurs import MESSAGES_EN, MESSAGES_FR

RACINE = Path(__file__).parent


class _Reponse:
    def __init__(self, data):
        self.data = data


class _Requete:
    def __init__(self, base, nom):
        self.base, self.nom = base, nom
        self.action = "select"
        self.filtres = []
        self.ordre = None
        self.limite = None
        self.ligne = None

    def select(self, *_):
        self.action = "select"
        return self

    def insert(self, ligne):
        self.action, self.ligne = "insert", dict(ligne)
        return self

    def delete(self):
        self.action = "delete"
        return self

    def eq(self, colonne, valeur):
        self.filtres.append((colonne, "eq", valeur))
        return self

    def is_(self, colonne, valeur):
        self.filtres.append((colonne, "is", None))
        return self

    def order(self, colonne, desc=False):
        self.ordre = (colonne, desc)
        return self

    def limit(self, n):
        self.limite = n
        return self

    def _garde(self, ligne):
        return all(ligne.get(c) == v for c, _, v in self.filtres)

    def execute(self):
        table = self.base.tables.setdefault(self.nom, [])
        if self.action == "insert":
            ligne = dict(self.ligne)
            ligne.setdefault("id", str(uuid.uuid4()))
            ligne.setdefault("cree_a", f"2026-11-18T10:00:{len(table):02d}Z")
            ligne.setdefault("profil_id", None)
            table.append(ligne)
            return _Reponse([ligne])
        if self.action == "delete":
            self.base.tables[self.nom] = [l for l in table if not self._garde(l)]
            return _Reponse([])
        lignes = [l for l in table if self._garde(l)]
        if self.ordre:
            lignes.sort(key=lambda l: l[self.ordre[0]], reverse=self.ordre[1])
        if self.limite is not None:
            lignes = lignes[: self.limite]
        return _Reponse(lignes)


class _FauxClient:
    def __init__(self):
        self.tables = {}

    def table(self, nom):
        return _Requete(self, nom)


def _son(octets=b"RIFF....WAVE"):
    return {"base64": base64.b64encode(octets).decode(), "duree_ms": 1200, "pics": [0.1, 0.9]}


class TestProfils(unittest.TestCase):
    def test_creer_et_lister(self):
        c = _FauxClient()
        p = creer_profil(c, "u1", "  Diarra ", "Fanta")
        self.assertEqual((p["nom"], p["prenom"]), ("Diarra", "Fanta"))
        self.assertEqual([x["id"] for x in lister_profils(c, "u1")], [p["id"]])
        self.assertEqual(lister_profils(c, "u2"), [])

    def test_nom_vide_ou_trop_long_refuse(self):
        c = _FauxClient()
        for nom, prenom in (("", "A"), ("A", "   "), ("x" * 61, "A")):
            with self.assertRaises(ErreurBambara) as e:
                creer_profil(c, "u1", nom, prenom)
            self.assertEqual(e.exception.code, "BAMBARA_PROFIL_NOM_INVALIDE")

    def test_nombre_maximum_de_profils(self):
        c = _FauxClient()
        for i in range(MAX_PROFILS_PAR_COMPTE):
            creer_profil(c, "u1", "N", f"P{i}")
        with self.assertRaises(ErreurBambara) as e:
            creer_profil(c, "u1", "N", "de plus")
        self.assertEqual(e.exception.code, "BAMBARA_TROP_DE_PROFILS")

    def test_profil_d_un_autre_compte_refuse(self):
        c = _FauxClient()
        p = creer_profil(c, "u1", "A", "B")
        with self.assertRaises(ErreurBambara) as e:
            lister_conversations(c, "u2", p["id"])
        self.assertEqual(e.exception.code, "BAMBARA_PROFIL_INTROUVABLE")

    def test_identifiant_de_profil_invalide(self):
        with self.assertRaises(ErreurBambara):
            normaliser_profil("pas-un-uuid")
        self.assertIsNone(normaliser_profil(""))
        self.assertIsNone(normaliser_profil(None))


class TestConversations(unittest.TestCase):
    def test_premier_message_ecrit_une_seule_fois(self):
        c = _FauxClient()
        cid = str(uuid.uuid4())
        self.assertFalse(enregistrer_premier_message(c, "u1", cid, None, "bonjour", None)["deja_enregistree"])
        self.assertTrue(enregistrer_premier_message(c, "u1", cid, None, "autre texte", None)["deja_enregistree"])
        lignes = lister_conversations(c, "u1", None)
        self.assertEqual([l["texte"] for l in lignes], ["bonjour"])

    def test_vocal_garde_a_part_et_relu(self):
        c = _FauxClient()
        cid = str(uuid.uuid4())
        enregistrer_premier_message(c, "u1", cid, None, None, _son())
        liste = lister_conversations(c, "u1", None)
        self.assertTrue(liste[0]["a_audio"])
        self.assertNotIn("audio_base64", liste[0])
        self.assertEqual(lire_audio(c, "u1", cid)["duree_ms"], 1200)
        with self.assertRaises(ErreurBambara):
            lire_audio(c, "u2", cid)

    def test_conversation_d_un_autre_compte_refusee(self):
        c = _FauxClient()
        cid = str(uuid.uuid4())
        enregistrer_premier_message(c, "u1", cid, None, "a", None)
        with self.assertRaises(ErreurBambara) as e:
            enregistrer_premier_message(c, "u2", cid, None, "b", None)
        self.assertEqual(e.exception.code, "BAMBARA_CONVERSATION_INTROUVABLE")

    def test_message_vide_et_audio_invalide_refuses(self):
        c = _FauxClient()
        with self.assertRaises(ErreurBambara) as e:
            enregistrer_premier_message(c, "u1", str(uuid.uuid4()), None, "  ", None)
        self.assertEqual(e.exception.code, "BAMBARA_MESSAGE_VIDE")
        for audio in ({"base64": "***pas du base64***", "duree_ms": 1, "pics": []}, {"base64": "A" * (LONGUEUR_MAX_AUDIO_BASE64 + 4), "duree_ms": 1, "pics": []}):
            with self.assertRaises(ErreurBambara) as e:
                enregistrer_premier_message(c, "u1", str(uuid.uuid4()), None, None, audio)
            self.assertEqual(e.exception.code, "BAMBARA_AUDIO_INVALIDE")

    def test_historique_separe_par_profil(self):
        c = _FauxClient()
        p = creer_profil(c, "u1", "A", "B")
        enregistrer_premier_message(c, "u1", str(uuid.uuid4()), p["id"], "du profil", None)
        enregistrer_premier_message(c, "u1", str(uuid.uuid4()), None, "commun", None)
        self.assertEqual([l["texte"] for l in lister_conversations(c, "u1", p["id"])], ["du profil"])
        self.assertEqual([l["texte"] for l in lister_conversations(c, "u1", None)], ["commun"])


class TestGardes(unittest.TestCase):
    def test_garder_deux_fois_ne_cree_qu_une_ligne(self):
        c = _FauxClient()
        a = garder(c, "u1", None, "video", "https://exemple.org/v.mp4", "Titre", None, None)
        b = garder(c, "u1", None, "video", "https://exemple.org/v.mp4", "Titre", None, None)
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(len(lister_gardes(c, "u1", None)), 1)

    def test_genre_et_adresse_invalides_refuses(self):
        c = _FauxClient()
        for genre, url in (("son", "https://x.org/a"), ("video", "javascript:alert(1)"), ("image", "")):
            with self.assertRaises(ErreurBambara) as e:
                garder(c, "u1", None, genre, url, "", None, None)
            self.assertEqual(e.exception.code, "BAMBARA_GARDE_INVALIDE")

    def test_retirer_ne_touche_que_ses_lignes(self):
        c = _FauxClient()
        g = garder(c, "u1", None, "image", "https://exemple.org/i.png", "", None, None)
        retirer_garde(c, "u2", g["id"])
        self.assertEqual(len(lister_gardes(c, "u1", None)), 1)
        retirer_garde(c, "u1", g["id"])
        self.assertEqual(lister_gardes(c, "u1", None), [])


class TestCodesEtCompte(unittest.TestCase):
    def test_chaque_code_existe_en_francais_et_en_anglais(self):
        source = (RACINE / "core" / "bambara_profils.py").read_text(encoding="utf-8")
        codes = set(re.findall(r'ErreurBambara\("([A-Z_]+)"\)', source))
        self.assertTrue(codes)
        for code in codes:
            self.assertIn(code, MESSAGES_FR, code)
            self.assertIn(code, MESSAGES_EN, code)
            self.assertNotIn("--", MESSAGES_FR[code])
            self.assertNotIn("--", MESSAGES_EN[code])

    def test_tables_dans_la_purge_et_l_export(self):
        purge = (RACINE / "core" / "purge_compte.py").read_text(encoding="utf-8")
        export = (RACINE / "api" / "profiles.py").read_text(encoding="utf-8")
        for table in ("bambara_gardes", "bambara_audios_messages", "bambara_audios", "bambara_conversations", "bambara_profils"):
            self.assertIn(f'"{table}"', purge, table)
        for table in ("bambara_profils", "bambara_conversations", "bambara_gardes"):
            self.assertIn(f'"{table}"', export, table)
        # L'audio est trop lourd pour l'export : seules les métadonnées des conversations en font partie.
        self.assertNotIn('"bambara_audios", "bambara_audios"', export)


if __name__ == "__main__":
    unittest.main()
