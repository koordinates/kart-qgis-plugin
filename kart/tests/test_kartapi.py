from qgis.testing import unittest, start_app

from kart.kartapi import kartVersionDetails
from kart.utils import setSetting, KARTPATH
from kart.tests.utils import patch_iface

start_app()


class TestKartapi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch_iface()

    def setUp(self):
        pass

    def test_error_wrong_kart_path(self):
        setSetting(KARTPATH, "wrongpath")
        ret = kartVersionDetails()
        assert "Kart is not correctly configured" in ret
