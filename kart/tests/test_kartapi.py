import os

from qgis.testing import unittest, start_app

from kart.kartapi import (
    kartVersionDetails,
    repos,
    addRepo,
    Repository,
    readReposFromSettings,
)
from kart.utils import setSetting, KARTPATH
from kart.tests.utils import patch_iface

start_app()

testRepoPath = os.path.join(os.path.dirname(__file__), "data", "testrepo")
TESTREPO = Repository(testRepoPath)


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

    def test_store_repos_in_settings(self):
        repositories = repos()
        assert not bool(repositories)
        validRepo = Repository(testRepoPath)
        addRepo(validRepo)
        invalidRepo = Repository("wrongpath")
        addRepo(invalidRepo)
        readReposFromSettings()
        repositories = repos()
        assert len(repositories) == 1
        assert repositories[0].path == testRepoPath

    def test_log(self):
        assert TESTREPO.isInitialized()
        log = TESTREPO.log()
        assert len(log) == 1
