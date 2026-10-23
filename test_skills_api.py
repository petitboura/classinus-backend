"""Tests de l'API des skills autonomes avec un faux stockage R2 et une fausse base."""
import logging
import os
import re
import types
import unittest
from types import SimpleNamespace


os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault(
    "SUPABASE_SECRET",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x",
)
logging.disable(logging.CRITICAL)


class FauxR2:
    def __init__(self):
        self.objets, self.echec_upload_sur = {}, None

    def upload(self, cle, contenu, options=None):
        if self.echec_upload_sur and cle.endswith(self.echec_upload_sur):
            raise RuntimeError("echec R2")
        self.objets[cle] = contenu

    def download(self, cle):
        return self.objets[cle]

    def remove(self, cles):
        for c in cles:
            self.objets.pop(c, None)


class Requete:
    def __init__(self, base, table):
        self.base, self.table, self.filtres, self.op, self.donnees = base, table, [], "select", None
        self.compte, self.un, self.conflit = False, False, None

    def select(self, *_, count=None, **__):
        self.compte = bool(count)
        return self

    def eq(self, c, v):
        self.filtres.append(lambda r: r.get(c) == v)
        return self

    def in_(self, c, vs):
        self.filtres.append(lambda r: r.get(c) in vs)
        return self

    def order(self, *_, **__):
        return self

    def limit(self, *_):
        return self

    def maybe_single(self):
        self.un = True
        return self

    def insert(self, d):
        self.op, self.donnees = "insert", d
        return self

    def upsert(self, d, on_conflict=None):
        self.op, self.donnees, self.conflit = "upsert", d, on_conflict
        return self

    def update(self, d):
        self.op, self.donnees = "update", d
        return self

    def delete(self):
        self.op = "delete"
        return self

    def execute(self):
        if self.base.echec_sur == (self.table, self.op):
            raise RuntimeError("echec base")
        lignes = self.base.tables.setdefault(self.table, [])
        sel = [r for r in lignes if all(f(r) for f in self.filtres)]
        if self.op == "insert":
            lignes.extend(dict(r) for r in (self.donnees if isinstance(self.donnees, list) else [self.donnees]))
        elif self.op == "upsert":
            cles = self.conflit.split(",")
            for d in self.donnees:
                ex = next((r for r in lignes if all(r.get(k) == d[k] for k in cles)), None)
                ex.update(d) if ex else lignes.append(dict(d))
        elif self.op == "update":
            for r in sel:
                r.update(self.donnees)
        elif self.op == "delete":
            self.base.tables[self.table] = [r for r in lignes if r not in sel]
        data = [dict(r) for r in sel]
        if self.un:
            return SimpleNamespace(data=data[0] if data else None)
        return SimpleNamespace(data=data, count=len(data))


class FausseBase:
    def __init__(self):
        self.tables, self.echec_sur = {}, None

    def table(self, nom):
        return Requete(self, nom)


r2, base = FauxR2(), FausseBase()
_stock = types.SimpleNamespace(from_=lambda bucket: r2)

from unittest import mock
from fastapi import HTTPException
from api import skills as S
from core.erreurs import MESSAGES_EN, MESSAGES_FR

U = SimpleNamespace(id="user-1")


def payload(nom="Mon skill", fichiers=None, description="d"):
    return S.SkillPayload(nom=nom, description=description, fichiers=[S.Fichier(chemin=c, contenu=t) for c, t in (fichiers or [])])


class TestSkills(unittest.TestCase):
    def setUp(self):
        for faux in (mock.patch.object(S, "supabase", base), mock.patch.object(S, "stockage_r2", _stock)):
            faux.start()
            self.addCleanup(faux.stop)
        r2.objets.clear(); r2.echec_upload_sur = None
        base.tables.clear(); base.echec_sur = None

    def test_modifier_avec_memes_chemins_conserve_les_fichiers(self):
        s = S.creer(payload(fichiers=[("SKILL.md", "un"), ("a/b.md", "deux")]), U)
        S.modifier(s["id"], payload(fichiers=[("SKILL.md", "un v2"), ("a/b.md", "deux v2")]), U)
        lu = {f["chemin"]: f["contenu"] for f in S.obtenir(s["id"], U)["fichiers"]}
        self.assertEqual(lu, {"SKILL.md": "un v2", "a/b.md": "deux v2"})
        self.assertEqual(len(r2.objets), 2, "les anciennes versions doivent être supprimées")

    def test_modifier_retire_les_fichiers_absents(self):
        s = S.creer(payload(fichiers=[("SKILL.md", "x"), ("vieux.md", "y")]), U)
        S.modifier(s["id"], payload(fichiers=[("SKILL.md", "x2")]), U)
        self.assertEqual([f["chemin"] for f in S.obtenir(s["id"], U)["fichiers"]], ["SKILL.md"])
        self.assertEqual(len(r2.objets), 1)

    def test_echec_envoi_pendant_modification_garde_l_ancienne_version(self):
        s = S.creer(payload(fichiers=[("SKILL.md", "ancien"), ("b.md", "b")]), U)
        r2.echec_upload_sur = "b.md"
        with self.assertRaises(HTTPException) as e:
            S.modifier(s["id"], payload(fichiers=[("SKILL.md", "nouveau"), ("b.md", "b2")]), U)
        self.assertEqual(e.exception.detail["code"], "IMPOSSIBLE_DE_MODIFIER_SKILL")
        r2.echec_upload_sur = None
        lu = {f["chemin"]: f["contenu"] for f in S.obtenir(s["id"], U)["fichiers"]}
        self.assertEqual(lu, {"SKILL.md": "ancien", "b.md": "b"})
        self.assertEqual(len(r2.objets), 2)

    def test_echec_base_pendant_modification_garde_l_ancienne_version(self):
        s = S.creer(payload(fichiers=[("SKILL.md", "ancien")]), U)
        base.echec_sur = ("skill_files", "upsert")
        with self.assertRaises(HTTPException):
            S.modifier(s["id"], payload(fichiers=[("SKILL.md", "nouveau")]), U)
        base.echec_sur = None
        self.assertEqual(S.obtenir(s["id"], U)["fichiers"][0]["contenu"], "ancien")
        self.assertEqual(len(r2.objets), 1)

    def test_echec_creation_ne_laisse_rien(self):
        base.echec_sur = ("skill_files", "insert")
        with self.assertRaises(HTTPException):
            S.creer(payload(fichiers=[("SKILL.md", "x")]), U)
        self.assertEqual(r2.objets, {})
        self.assertEqual(base.tables.get("skills", []), [])

    def test_entete_genere_est_protege(self):
        s = S.creer(payload(nom='a" ou autre', description="ok"), U)
        contenu = S.obtenir(s["id"], U)["fichiers"][0]["contenu"]
        self.assertEqual(len([l for l in contenu.splitlines() if l.startswith("name:")]), 1)

    def test_saut_de_ligne_refuse_dans_le_nom(self):
        with self.assertRaises(HTTPException) as e:
            S.creer(payload(nom="a\nname: pirate"), U)
        self.assertEqual(e.exception.detail["code"], "NOM_SKILL_INVALIDE")

    def test_chemin_invalide_et_doublon(self):
        for fichiers, code in ((([("../x", "a")]), "CHEMIN_FICHIER_INVALIDE"), ([("a", "1"), ("a", "2")], "CHEMIN_FICHIER_DUPLIQUE")):
            with self.assertRaises(HTTPException) as e:
                S.creer(payload(fichiers=fichiers), U)
            self.assertEqual(e.exception.detail["code"], code)

    def test_fichier_non_texte_ne_bloque_pas_la_lecture(self):
        s = S.creer(payload(fichiers=[("SKILL.md", "ok")]), U)
        cle = base.tables["skill_files"][0]["cle_stockage"]
        r2.objets[cle + "x"] = b"\xff\xfe"
        base.tables["skill_files"].append({"skill_id": s["id"], "chemin": "bin.dat", "cle_stockage": cle + "x", "type_mime": "application/octet-stream", "taille_octets": 2})
        lu = {f["chemin"]: f for f in S.obtenir(s["id"], U)["fichiers"]}
        self.assertTrue(lu["bin.dat"]["binaire"])
        self.assertIsNone(lu["bin.dat"]["contenu"])

    def test_taille_totale_refusee(self):
        gros = "x" * (S.TAILLE_FICHIER_MAX)
        n = S.TAILLE_TOTALE_MAX // S.TAILLE_FICHIER_MAX + 1
        with self.assertRaises(HTTPException) as e:
            S.creer(payload(fichiers=[(f"f{i}.md", gros) for i in range(n)]), U)
        self.assertEqual(e.exception.detail["code"], "SKILL_TROP_VOLUMINEUX")

    def test_limite_de_skills_par_compte(self):
        ancien = S.NB_SKILLS_MAX
        S.NB_SKILLS_MAX = 1
        try:
            S.creer(payload(), U)
            with self.assertRaises(HTTPException) as e:
                S.creer(payload(nom="autre"), U)
            self.assertEqual(e.exception.detail["code"], "SKILLS_LIMITE_ATTEINTE")
        finally:
            S.NB_SKILLS_MAX = ancien

    def test_suppression_retire_tout(self):
        s = S.creer(payload(fichiers=[("SKILL.md", "x")]), U)
        S.supprimer(s["id"], U)
        self.assertEqual(r2.objets, {})

    def test_tous_les_codes_utilises_sont_declares_en_fr_et_en(self):
        with open(S.__file__, encoding="utf-8") as fichier:
            source = fichier.read()
        codes = set(re.findall(r'erreur_api\(\d+,\s*"([A-Z_]+)"', source))
        self.assertTrue(codes)
        for code in codes:
            self.assertIn(code, MESSAGES_FR, code)
            self.assertIn(code, MESSAGES_EN, code)
            self.assertNotIn(" -- ", MESSAGES_FR[code] + MESSAGES_EN[code])


if __name__ == "__main__":
    unittest.main()
