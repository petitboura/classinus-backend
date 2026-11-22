"""Tests de la synchronisation des skills officiels au démarrage : jamais bloquante, désactivable."""
import os
import sys
import types
import unittest
from unittest import mock

from core import synchro_skills_demarrage as module


def _faux_script(synchroniser):
    faux = types.ModuleType("scripts.synchroniser_skills_plateforme")
    faux.synchroniser = synchroniser
    faux.afficher = mock.Mock()
    return faux


class TestSynchroDemarrage(unittest.IsolatedAsyncioTestCase):
    async def test_lance_la_synchronisation_quand_active(self):
        synchroniser = mock.Mock(return_value={"erreurs": []})
        faux = _faux_script(synchroniser)
        with mock.patch.dict(os.environ, {"SKILLS_PLATEFORME_SYNCHRO": ""}), \
                mock.patch.dict(sys.modules, {"scripts.synchroniser_skills_plateforme": faux}), \
                mock.patch("scripts.synchroniser_skills_plateforme", faux, create=True):
            await module.synchroniser_au_demarrage()
        synchroniser.assert_called_once_with(True)
        faux.afficher.assert_called_once()

    async def test_desactivee_par_la_variable(self):
        synchroniser = mock.Mock()
        faux = _faux_script(synchroniser)
        for valeur in ("non", "0", "false", "OFF"):
            with mock.patch.dict(os.environ, {"SKILLS_PLATEFORME_SYNCHRO": valeur}), \
                    mock.patch.dict(sys.modules, {"scripts.synchroniser_skills_plateforme": faux}), \
                    mock.patch("scripts.synchroniser_skills_plateforme", faux, create=True):
                await module.synchroniser_au_demarrage()
        synchroniser.assert_not_called()

    async def test_une_erreur_ne_remonte_jamais(self):
        faux = _faux_script(mock.Mock(side_effect=RuntimeError("R2 injoignable")))
        with mock.patch.dict(os.environ, {"SKILLS_PLATEFORME_SYNCHRO": ""}), \
                mock.patch.dict(sys.modules, {"scripts.synchroniser_skills_plateforme": faux}), \
                mock.patch("scripts.synchroniser_skills_plateforme", faux, create=True):
            with self.assertLogs(level="ERROR"):
                await module.synchroniser_au_demarrage()


if __name__ == "__main__":
    unittest.main()
