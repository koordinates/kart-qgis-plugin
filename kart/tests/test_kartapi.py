import os
import tempfile

from qgis.core import edit
from qgis.testing import unittest, start_app

from kart.kartapi import (
    kartVersionDetails,
    repos,
    addRepo,
    Repository,
    readReposFromSettings,
    installedVersion,
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
        setSetting(KARTPATH, "")

    def testErrorWrongKartPath(self):
        setSetting(KARTPATH, "wrongpath")
        ret = kartVersionDetails()
        assert "Kart is not correctly configured" in ret

    def testKartVersion(self):
        version = installedVersion()
        assert version == "0.10.6"

    def testStoreReposInSettings(self):
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

    def testInit(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(folder)
            assert not repo.isInitialized()
            repo.init()
            assert repo.isInitialized()

    def testImport(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(folder)
            repo.init()
            assert repo.isInitialized()
            repo.configureUser("user", "user@user.use")
            gkpgPath = os.path.join(
                os.path.dirname(__file__), "data", "layers", "testlayer.gpkg"
            )
            repo.importGpkg(gkpgPath)
            vectorLayers, tables = repo.datasets()
            assert vectorLayers == ["testlayer"]

    def testDatasets(self):
        vectorLayers, tables = TESTREPO.datasets()
        assert vectorLayers == ["testlayer"]
        assert tables == []

    def testClone(self):
        with tempfile.TemporaryDirectory() as folder:
            clone = Repository.clone(TESTREPO.path, folder)
            assert clone.isInitialized()
            clonedLog = clone.log()
            log = TESTREPO.log()
            assert len(clonedLog) > 0
            assert len(clonedLog) == len(log)

    def testLog(self):
        assert TESTREPO.isInitialized()
        log = TESTREPO.log()
        assert len(log) == 5
        assert "Deleted" in log[0]["message"]
        assert "Modified" in log[1]["message"]
        assert "Modified" in log[2]["message"]
        assert "Added" in log[3]["message"]

    def testDiff(self):
        diff = TESTREPO.diff("HEAD", "HEAD~1")
        assert "testlayer" in diff
        features = diff["testlayer"]
        assert len(features) == 1
        assert features[0]["id"].startswith("D::")

        diff = TESTREPO.diff("HEAD~1", "HEAD~2")
        assert "testlayer" in diff
        features = diff["testlayer"]
        assert len(features) == 2
        assert features[0]["geometry"] == features[1]["geometry"]

    def testCreateAndDeleteBranch(self):
        TESTREPO.createBranch("mynewbranch")
        branches = TESTREPO.branches()
        assert "mynewbranch" in branches
        TESTREPO.deleteBranch("mynewbranch")
        assert "mynewbranch" not in branches

    def testBranches(self):
        branches = TESTREPO.branches()
        assert len(branches) == 2

    def testCurrentBranch(self):
        current = TESTREPO.currentBranch()
        assert current == "main"
        TESTREPO.checkoutBranch("anotherbranch")
        current = TESTREPO.currentBranch()
        assert current == "anotherbranch"

    def testModifyLayerAndRestore(self):
        layer = TESTREPO.workingCopyLayer("testlayer")
        feature = list(layer.getFeatures())[0]
        with edit(layer):
            layer.deleteFeatures(feature.id())
        diff = TESTREPO.diff()
        assert "testlayer" in diff
        TESTREPO.restore("HEAD")
        diff = TESTREPO.diff()
        assert not bool(diff.get("testlayer", []))
