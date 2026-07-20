import os
import re
import shutil
import tempfile

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsReferencedRectangle,
    edit,
)
from qgis.PyQt.QtTest import QSignalSpy
from qgis.testing import start_app, unittest

from kart.core import RepoManager
from kart.kartapi import (
    KartException,
    Repository,
    executeKart,
    installedVersion,
    kartVersionDetails,
)
from kart.tests.utils import patch_iface
from kart.utils import HELPERMODE, KARTPATH, setSetting

start_app()

testRepoPath = os.path.join(os.path.dirname(__file__), "data", "testrepo")


def createRepoCopy():
    tempFolder = tempfile.TemporaryDirectory()
    dst = os.path.join(tempFolder.name, "testrepo")
    shutil.copytree(testRepoPath, dst)
    with open(os.path.join(dst, ".git"), "w") as f:
        f.write("gitdir: .kart")
    repoCopy = Repository(dst)
    repoCopy.configureUser("user", "user@user.use")
    return tempFolder, repoCopy


class TestKartapi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch_iface()
        cls.tempFolder, cls.testRepo = createRepoCopy()

    @classmethod
    def tearDownClass(cls):
        cls.tempFolder.cleanup()

    def setUp(self):
        setSetting(KARTPATH, "")

    def testErrorWrongKartPath(self):
        setSetting(KARTPATH, "wrongpath")
        ret = kartVersionDetails()
        assert "Kart is not correctly configured" in ret

    def testEnableUseHelper(self):
        setSetting(HELPERMODE, True)
        kartVersionDetails()  # called to set up environment var
        assert executeKart.env["KART_USE_HELPER"] == "1", "Helper mode was not enabled"

    def testChangeHelperMode(self):
        """
        KART_USE_HELPER should be set each time executeKart is called so
        a change of setting is applied appropriately
        """
        setSetting(HELPERMODE, True)
        kartVersionDetails()  # called to set up environment var
        setSetting(HELPERMODE, False)
        kartVersionDetails()  # called to set up environment var
        assert executeKart.env["KART_USE_HELPER"] == "", "Helper mode was not disabled"

    def testKartVersion(self):
        version = installedVersion()
        assert re.match(r"\d+\.\d+\.\d+", version)

    def testDecodesNonUtf8Output(self):
        """
        Kart's --version banner contains a '»' (0xbb) encoded in the Windows
        ANSI codepage. Under QGIS 4 / Python UTF-8 mode the preferred encoding
        is utf-8, where 0xbb is invalid and previously crashed the subprocess
        reader thread, returning empty output (issue #137). Output must decode
        without raising.
        """
        with tempfile.TemporaryDirectory() as folder:
            fakeKart = os.path.join(folder, "kart")
            with open(fakeKart, "w") as f:
                f.write(
                    "#!/usr/bin/env python3\n"
                    "import sys\n"
                    r"sys.stdout.buffer.write(b'Kart v1.2.3\n\xbb GDAL v3.8.5\n')"
                    "\n"
                )
            os.chmod(fakeKart, 0o755)
            setSetting(KARTPATH, folder)
            output = executeKart(["--version"])
            assert output.startswith("Kart v1.2.3")

    def testDecodesUtf8JsonData(self):
        """
        Kart's JSON output is utf-8 (msgspec writes raw utf-8 bytes), so
        non-ASCII data must be decoded as utf-8 and not the locale codepage,
        which would silently corrupt it (e.g. on a Windows cp1252 locale).
        """
        with tempfile.TemporaryDirectory() as folder:
            fakeKart = os.path.join(folder, "kart")
            with open(fakeKart, "w", encoding="utf-8") as f:
                f.write(
                    "#!/usr/bin/env python3\n"
                    "import sys\n"
                    'sys.stdout.buffer.write(\'{"name": "café"}\''
                    ".encode('utf-8'))\n"
                )
            os.chmod(fakeKart, 0o755)
            setSetting(KARTPATH, folder)
            output = executeKart(["data"], jsonoutput=True)
            assert output == {"name": "café"}

    def testStoreReposInSettings(self):
        manager = RepoManager()
        assert not manager.repos()

        spy = QSignalSpy(manager.repo_added)
        manager.add_repo(self.testRepo)

        self.assertEqual(len(spy), 1)
        self.assertEqual(spy[-1][0], self.testRepo)

        invalidRepo = Repository("wrongpath")
        manager.add_repo(invalidRepo)

        manager2 = RepoManager()
        assert len(manager2.repos()) == 1
        assert manager2.repos()[0].path == self.testRepo.path

        remove_spy = QSignalSpy(manager2.repo_removed)
        manager2.remove_repo(self.testRepo)
        self.assertEqual(len(remove_spy), 1)
        self.assertEqual(remove_spy[-1][0], self.testRepo)
        assert not manager2.repos()

        manager3 = RepoManager()
        self.assertEqual(len(manager3.repos()), 0)

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
            gkpgPath = os.path.join(os.path.dirname(__file__), "data", "layers", "testlayer.gpkg")
            repo.importIntoRepo(gkpgPath)
            vectorLayers, tables = repo.datasets()
            assert vectorLayers == ["testlayer"]

    def testDatasets(self):
        vectorLayers, tables = self.testRepo.datasets()
        assert vectorLayers == ["testlayer"]
        assert tables == []

    def testClone(self):
        with tempfile.TemporaryDirectory() as folder:
            clone = Repository.clone(self.testRepo.path, folder)
            assert clone.isInitialized()
            clonedLog = clone.log()
            log = self.testRepo.log()
            assert len(clonedLog) > 0
            assert len(clonedLog) == len(log)

    def testLog(self):
        log = self.testRepo.log()
        assert len(log) == 5
        assert "Deleted" in log[0]["message"]
        assert "Modified" in log[1]["message"]
        assert "Modified" in log[2]["message"]
        assert "Added" in log[3]["message"]

    def testLogForDataset(self):
        log = self.testRepo.log(dataset="testlayer")
        assert len(log) == 5
        assert "Deleted" in log[0]["message"]
        assert "Modified" in log[1]["message"]
        assert "Modified" in log[2]["message"]
        assert "Added" in log[3]["message"]

    def testLogForMissingDataset(self):
        log = self.testRepo.log(dataset="wronglayer")
        assert len(log) == 0

    def testDiff(self):
        diff = self.testRepo.diff("HEAD", "HEAD~1")
        assert "testlayer" in diff
        features = diff["testlayer"]
        assert len(features) == 1
        assert features[0]["id"].endswith(":D")

        diff = self.testRepo.diff("HEAD~1", "HEAD~2")
        assert "testlayer" in diff
        features = diff["testlayer"]
        assert len(features) == 2
        assert features[0]["geometry"] == features[1]["geometry"]

    def testCreateAndDeleteBranch(self):
        self.testRepo.createBranch("mynewbranch")
        branches = self.testRepo.branches()
        assert "mynewbranch" in branches
        self.testRepo.deleteBranch("mynewbranch")
        branches = self.testRepo.branches()
        assert "mynewbranch" not in branches

    def testBranches(self):
        branches = self.testRepo.branches()
        assert len(branches) == 2

    def testCurrentBranch(self):
        current = self.testRepo.currentBranch()
        assert current == "main"
        self.testRepo.checkoutBranch("anotherbranch")
        current = self.testRepo.currentBranch()
        assert current == "anotherbranch"

    def testModifyLayerAndRestore(self):
        folder, repo = createRepoCopy()
        layer = repo.workingCopyLayer("testlayer")
        feature = list(layer.getFeatures())[0]
        with edit(layer):
            layer.deleteFeatures([feature.id()])
        diff = repo.diff()
        assert "testlayer" in diff
        repo.restore("HEAD")
        diff = repo.diff()
        assert not bool(diff.get("testlayer", []))
        folder.cleanup()

    def testCommit(self):
        folder, repo = createRepoCopy()
        layer = repo.workingCopyLayer("testlayer")
        feature = list(layer.getFeatures())[0]
        with edit(layer):
            layer.deleteFeatures([feature.id()])
        repo.commit("A new commit")
        log = repo.log()
        assert log[0]["message"] == "A new commit"
        diff = repo.diff("HEAD", "HEAD~1")
        assert "testlayer" in diff
        features = diff["testlayer"]
        assert len(features) == 1
        assert features[0]["id"].endswith(":D")
        folder.cleanup()

    def testSetSpatialFilter(self):
        folder, repo = createRepoCopy()
        assert repo.spatialFilter() is None
        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        rect = QgsRectangle(0, 0, 1, 1)
        referencedRectangle = QgsReferencedRectangle(rect, crs)
        repo.setSpatialFilter(referencedRectangle)
        assert repo.spatialFilter() is not None
        repo.setSpatialFilter()
        assert repo.spatialFilter() is None
        folder.cleanup()

    def testDatasetNameFromLayer(self):
        layer = self.testRepo.workingCopyLayer("testlayer")
        assert self.testRepo.datasetNameFromLayer(layer) == "testlayer"

    def testWorkingCopyLayerIdField(self):
        assert "fid" == self.testRepo.workingCopyLayerIdField("testlayer")

    def testWorkingCopyLayerCrs(self):
        assert "EPSG:4326" == self.testRepo.workingCopyLayerCrs("testlayer")

    def testDeleteDataset(self):
        folder, repo = createRepoCopy()
        ncommits = len(repo.log())
        assert "testlayer" in repo.datasets()[0]
        repo.deleteDataset("testlayer")
        assert ncommits + 1 == len(repo.log())
        assert "testlayer" not in repo.datasets()[0]
        folder.cleanup()

    def testBranchAndMerge(self):
        folder, repo = createRepoCopy()
        repo.createBranch("newbranch")
        assert "newbranch" in repo.branches()
        repo.checkoutBranch("newbranch")
        assert "newbranch" == repo.currentBranch()
        layer = repo.workingCopyLayer("testlayer")
        with edit(layer):
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
            feature.setAttributes([5, 5])
            layer.addFeatures([feature])
        repo.commit("A new commit")
        repo.checkoutBranch("main")
        assert "main" == repo.currentBranch()
        log = repo.log()
        assert log[0]["message"] != "A new commit"
        repo.mergeBranch("newbranch", "")
        log = repo.log()
        assert log[0]["message"] == "A new commit"
        folder.cleanup()

    """
    def testBranchAndMergeWithDelete(self):
        folder, repo = createRepoCopy()
        repo.createBranch("newbranch")
        assert "newbranch" in repo.branches()
        repo.checkoutBranch("newbranch")
        assert "newbranch" == repo.currentBranch()
        layer = repo.workingCopyLayer("testlayer")
        feature = list(layer.getFeatures())[0]
        with edit(layer):
            layer.deleteFeatures([feature.id()])
        repo.commit("A new commit")
        repo.checkoutBranch("main")
        assert "main" == repo.currentBranch()
        log = repo.log()
        assert log[0]["message"] != "A new commit"
        repo.mergeBranch("newbranch", "")
        log = repo.log()
        assert log[0]["message"] == "A new commit"
        folder.cleanup()
    """

    def testTags(self):
        folder, repo = createRepoCopy()
        assert repo.tags() == []
        repo.createTag("mytag", "HEAD")
        assert repo.tags() == ["mytag"]
        repo.deleteTag("mytag")
        assert repo.tags() == []
        folder.cleanup()

    def testCloneAuthFailed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(KartException):
                Repository.clone(
                    "https://kart:abcdefghijklmnop@data.koordinates.com/"
                    "land-information-new-zealand/layer-50804",
                    folder,
                )
