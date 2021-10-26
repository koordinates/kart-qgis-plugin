import os
import tempfile

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QTreeWidgetItem,
    QAbstractItemView,
    QFileDialog,
    QAction,
    QMenu,
    QInputDialog,
    QMessageBox,
)

from qgis.utils import iface
from qgis.core import Qgis, QgsVectorLayer, QgsVectorFileWriter, QgsProject

from kart.kartapi import (
    repos,
    addRepo,
    removeRepo,
    Repository,
    executeskart,
    KartException,
)
from kart.gui.diffviewer import DiffViewerDialog
from kart.gui.historyviewer import HistoryDialog
from kart.gui.conflictsdialog import ConflictsDialog
from kart.gui.clonedialog import CloneDialog
from kart.gui.pushdialog import PushDialog
from kart.gui.pulldialog import PullDialog
from kart.gui.initdialog import InitDialog
from kart.gui.mergedialog import MergeDialog
from kart.gui.switchdialog import SwitchDialog
from kart.gui.repopropertiesdialog import RepoPropertiesDialog
from kart.utils import layerFromSource

pluginPath = os.path.split(os.path.dirname(__file__))[0]


def icon(f):
    return QIcon(os.path.join(pluginPath, "img", f))


repoIcon = icon("repository.png")
addRepoIcon = icon("addrepo.png")
createRepoIcon = icon("createrepo.png")
cloneRepoIcon = icon("clone.png")
logIcon = icon("log.png")
importIcon = icon("import.png")
checkoutIcon = icon("checkout.png")
commitIcon = icon("commit.png")
discardIcon = icon("reset.png")
layerIcon = icon("layer.png")
mergeIcon = icon("merge.png")
addtoQgisIcon = icon("openinqgis.png")
diffIcon = icon("changes.png")
abortIcon = icon("abort.png")
resolveIcon = icon("resolve.png")
pushIcon = icon("push.png")
pullIcon = icon("pull.png")
removeIcon = icon("remove.png")
refreshIcon = icon("refresh.png")
propertiesIcon = icon("info.png")
patchIcon = icon("patch.png")

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "dockwidget.ui"))


class KartDockWidget(BASE, WIDGET):
    def __init__(self):
        super(QDockWidget, self).__init__(iface.mainWindow())
        self.setupUi(self)

        pixmap = QPixmap(
            os.path.join(pluginPath, "img", "karticon.png")
        ).scaledToHeight(self.labelHeaderText.height() * 2)
        self.labelHeaderIcon.setPixmap(pixmap)
        self.tree.setFocusPolicy(Qt.NoFocus)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.customContextMenuRequested.connect(self.showPopupMenu)

        def onItemExpanded(item):
            if hasattr(item, "onExpanded"):
                item.onExpanded()

        self.tree.itemExpanded.connect(onItemExpanded)

        self.fillTree()

    def fillTree(self):
        self.tree.clear()
        self.reposItem = ReposItem()
        self.tree.addTopLevelItem(self.reposItem)

    def showPopupMenu(self, point):
        item = self.tree.currentItem()
        self.menu = self.createMenu(item)
        point = self.tree.mapToGlobal(point)
        self.menu.popup(point)

    def createMenu(self, item):
        def _f(f, *args):
            def wrapper():
                f(*args)

            return wrapper

        menu = QMenu()
        for text, func, icon in item.actions():
            if func is None:
                menu.addSeparator()
            else:
                action = QAction(icon, text, menu)
                action.triggered.connect(_f(func))
                menu.addAction(action)

        return menu


class RefreshableItem(QTreeWidgetItem):
    def actions(self):
        actions = [
            ("Refresh", self.refreshContent, refreshIcon),
            ("divider", None, None),
        ]
        actions.extend(self._actions())
        return actions

    def refreshContent(self):
        self.takeChildren()
        self.populate()


class ReposItem(RefreshableItem):
    def __init__(self):
        QTreeWidgetItem.__init__(self)

        self.setText(0, "Repositories")
        self.setIcon(0, repoIcon)
        self.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

        self.populated = False
        # self.populate()

    def onExpanded(self):
        if not self.populated:
            self.populate()

    def populate(self):
        for repo in repos():
            item = RepoItem(repo)
            self.addChild(item)
        self.populated = True

    def _actions(self):
        actions = [
            ("Add existing repository...", self.addRepo, addRepoIcon),
            ("Create new repository...", self.createRepo, createRepoIcon),
            ("Clone repository...", self.cloneRepo, cloneRepoIcon),
        ]

        return actions

    def addRepo(self):
        folder = QFileDialog.getExistingDirectory(
            iface.mainWindow(), "Repository Folder", ""
        )
        if folder:
            repo = Repository(folder)
            if repo.isInitialized():
                item = RepoItem(repo)
                self.addChild(item)
                addRepo(repo)
            else:
                iface.messageBar().pushMessage(
                    "Error",
                    "The selected folder is not a Kart repository",
                    level=Qgis.Warning,
                )

    @executeskart
    def createRepo(self):
        dialog = InitDialog()
        ret = dialog.exec()
        if ret == dialog.Accepted:
            try:
                os.makedirs(dialog.folder)
            except FileExistsError:
                iface.messageBar().pushMessage(
                    "Error", "The specified folder already exists", level=Qgis.Warning
                )
                return
            repo = Repository(dialog.folder)
            repo.init(dialog.location)
            if repo.isInitialized():
                item = RepoItem(repo)
                self.addChild(item)
                addRepo(repo)
            else:
                iface.messageBar().pushMessage(
                    "Error", "Could not initialize repository", level=Qgis.Warning
                )

    @executeskart
    def cloneRepo(self):
        dialog = CloneDialog()
        dialog.show()
        ret = dialog.exec_()
        if ret == dialog.Accepted:
            repo = Repository.clone(
                dialog.src, dialog.dst, dialog.location, dialog.extent
            )
            item = RepoItem(repo)
            self.addChild(item)
            addRepo(repo)


class RepoItem(RefreshableItem):
    def __init__(self, repo):
        QTreeWidgetItem.__init__(self)
        self.repo = repo

        try:
            title = f"{repo.title() or os.path.normpath(repo.path)} [{repo.currentBranch()}]"
        except KartException:
            title = f"{repo.title() or os.path.normpath(repo.path)}"
        self.setText(0, title)
        self.setIcon(0, repoIcon)
        self.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

        self.populated = False

    def onExpanded(self):
        if not self.populated:
            self.populate()

    def populate(self):
        self.layersItem = LayersItem(self.repo)
        self.addChild(self.layersItem)
        self.populated = True

    def _actions(self):
        actions = [
            ("Remove this repository", self.removeRepository, removeIcon),
            ("Properties...", self.showProperties, propertiesIcon),
            ("divider", None, None),
        ]
        if self.repo.isMerging():
            actions.extend(
                [
                    ("Resolve conflicts...", self.resolveConflicts, resolveIcon),
                    ("Continue merge", self.continueMerge, mergeIcon),
                    ("Abort merge", self.abortMerge, abortIcon),
                ]
            )
        else:
            actions.extend(
                [
                    ("Show log...", self.showLog, logIcon),
                    ("Show working tree changes...", self.showChanges, diffIcon),
                    ("Discard working tree changes", self.discardChanges, discardIcon),
                    ("Commit working tree changes...", self.commitChanges, commitIcon),
                    ("Switch branch...", self.switchBranch, checkoutIcon),
                    ("Merge into current branch...", self.mergeBranch, mergeIcon),
                    ("divider", None, None),
                    ("Import layer into repo...", self.importLayer, importIcon),
                    ("divider", None, None),
                    ("Pull...", self.pull, pullIcon),
                    ("Push...", self.push, pushIcon),
                    ("divider", None, None),
                    ("Apply patch...", self.applyPatch, patchIcon),
                ]
            )

        return actions

    def showProperties(self):
        dialog = RepoPropertiesDialog(self.repo)
        dialog.show()
        dialog.exec()
        self.setText(0, self.repo.title() or os.path.normpath(self.repo.path))

    def removeRepository(self):
        self.parent().takeChild(self.parent().indexOfChild(self))
        removeRepo(self.repo)

    @executeskart
    def showLog(self):
        dialog = HistoryDialog(self.repo)
        dialog.exec()

    @executeskart
    def importLayer(self):
        filename, _ = QFileDialog.getOpenFileName(
            iface.mainWindow(), "Select vector layer to import", "", "*.*"
        )
        if filename:
            if os.path.splitext(filename)[-1].lower() != ".gpkg":
                layer = QgsVectorLayer(filename, "", "ogr")
                if not layer.isValid():
                    iface.messageBar().pushMessage(
                        "Import",
                        "The selected file is not a valid vector layer",
                        level=Qgis.Warning,
                    )
                    return
                tmpfolder = tempfile.TemporaryDirectory()
                filename = os.path.splitext(os.path.basename(filename))[0]
                gpkgfilename = os.path.join(tmpfolder.name, f"{filename}.gpkg")
                ret = QgsVectorFileWriter.writeAsVectorFormat(
                    layer, gpkgfilename, "utf-8", layer.crs()
                )
                if ret == QgsVectorFileWriter.NoError:
                    iface.messageBar().pushMessage(
                        "Import",
                        "Could not convert the selected layer to a gpkg file",
                        level=Qgis.Warning,
                    )
            else:
                tmpfolder = None
                gpkgfilename = filename
            self.repo.importGpkg(gpkgfilename)
            iface.messageBar().pushMessage(
                "Import", "Layer correctly imported", level=Qgis.Info
            )
            if self.populated:
                self.layersItem.refreshContent()
            if tmpfolder is not None:
                tmpfolder.cleanup()

    @executeskart
    def commitChanges(self):
        if self.repo.isMerging():
            iface.messageBar().pushMessage(
                "Commit",
                "Cannot commit if repository while repository is in merging status",
                level=Qgis.Warning,
            )
        elif self.repo.isWorkingTreeClean():
            iface.messageBar().pushMessage(
                "Commit", "Nothing to commit", level=Qgis.Warning
            )
        else:
            msg, ok = QInputDialog.getMultiLineText(
                iface.mainWindow(), "Commit", "Enter commit message:"
            )
            if ok and msg:
                if self.repo.commit(msg):
                    iface.messageBar().pushMessage(
                        "Commit", "Changes correctly committed", level=Qgis.Info
                    )
                else:
                    iface.messageBar().pushMessage(
                        "Commit", "Changes could not be commited", level=Qgis.Warning
                    )

    @executeskart
    def showChanges(self):
        changes = self.repo.diff()
        hasChanges = any([bool(layerchanges) for layerchanges in changes.values()])
        if hasChanges:
            dialog = DiffViewerDialog(iface.mainWindow(), changes, self.repo)
            dialog.exec()
        else:
            iface.messageBar().pushMessage(
                "Changes",
                "There are no changes in the working tree",
                level=Qgis.Warning,
            )

    @executeskart
    def switchBranch(self):
        dialog = SwitchDialog(self.repo)
        if dialog.exec() == dialog.Accepted:
            self.repo.checkoutBranch(dialog.branch, dialog.force)

    @executeskart
    def mergeBranch(self):
        dialog = MergeDialog(self.repo)
        if dialog.exec() == dialog.Accepted:
            conflicts = self.repo.mergeBranch(
                dialog.ref, msg=dialog.message, noff=dialog.noff, ffonly=dialog.ffonly
            )
            if conflicts:
                QMessageBox.warning(
                    iface.mainWindow(),
                    "Merge",
                    "There were conflicts during the merge operation.\n"
                    "Resolve them and then commit your changes to \n"
                    "complete the merge.",
                )
            else:
                iface.messageBar().pushMessage(
                    "Merge", "Branch correctly merged", level=Qgis.Info
                )

    @executeskart
    def discardChanges(self):
        self.repo.restore("HEAD")
        iface.messageBar().pushMessage(
            "Discard changes",
            "Working tree changes have been discarded",
            level=Qgis.Info,
        )

    @executeskart
    def continueMerge(self):
        if self.repo.conflicts():
            iface.messageBar().pushMessage(
                "Merge",
                "Cannot continue. There are merge conflicts.",
                level=Qgis.Warning,
            )
        else:
            self.repo.continueMerge()
            iface.messageBar().pushMessage(
                "Merge",
                "Merge operation was correctly continued and closed",
                level=Qgis.Info,
            )

    @executeskart
    def abortMerge(self):
        self.repo.abortMerge()
        iface.messageBar().pushMessage(
            "Merge", "Merge operation was correctly aborted", level=Qgis.Info
        )

    @executeskart
    def resolveConflicts(self):
        conflicts = self.repo.conflicts()
        if conflicts:
            dialog = ConflictsDialog(conflicts)
            dialog.exec()
            if dialog.okToMerge:
                self.repo.resolveConflicts(dialog.resolvedFeatures)
                self.repo.continueMerge()
                iface.messageBar().pushMessage(
                    "Merge",
                    "Merge operation was correctly continued and closed",
                    level=Qgis.Info,
                )
        else:
            iface.messageBar().pushMessage(
                "Resolve", "There are no conflicts to resolve", level=Qgis.Warning
            )

    @executeskart
    def push(self):
        dialog = PushDialog(self.repo)
        if dialog.exec() == dialog.Accepted:
            remote, branch, pushall = dialog.result
            self.repo.push(dialog.remote, dialog.branch, dialog.pushall)

    @executeskart
    def pull(self):
        dialog = PullDialog(self.repo)
        if dialog.exec() == dialog.Accepted:
            ret = self.repo.pull(dialog.remote, dialog.branch)
            if not ret:
                QMessageBox.warning(
                    iface.mainWindow(),
                    "Pull",
                    "There were conflicts during the pull operation.\n"
                    "Resolve them and then commit your changes to \n"
                    "complete it.",
                )
            else:
                iface.messageBar().pushMessage(
                    "Pull", "Pull correctly performed", level=Qgis.Info
                )

    @executeskart
    def applyPatch(self):
        filename, _ = QFileDialog.getOpenFileName(
            iface.mainWindow(),
            "Patch file",
            "",
            "Patch files (*.patch);;All files (*.*)",
        )
        if filename:
            self.repo.applyPatch(filename)
            iface.messageBar().pushMessage(
                "Apply patch",
                "Patch was correctly applied to working copy",
                level=Qgis.Info,
            )


class LayersItem(RefreshableItem):
    def __init__(self, repo):
        QTreeWidgetItem.__init__(self)

        self.repo = repo

        self.setText(0, "Layers")
        self.setIcon(0, layerIcon)

        self.populate()

    @executeskart
    def populate(self):
        layers = self.repo.layers()
        for layer in layers:
            item = LayerItem(layer, self.repo)
            self.addChild(item)

    def _actions(self):
        return []


class LayerItem(QTreeWidgetItem):
    def __init__(self, layername, repo):
        QTreeWidgetItem.__init__(self)
        self.layername = layername
        self.repo = repo

        self.setText(0, layername)
        self.setIcon(0, layerIcon)

    def actions(self):
        actions = [
            ("Show log...", self.showLog, logIcon),
            ("Add to QGIS project", self.addToProject, addtoQgisIcon),
            ("Remove from repository", self.removeFromRepo, removeIcon),
        ]

        if not self.repo.isMerging():
            actions.append(
                ("Commit working tree changes...", self.commitChanges, commitIcon)
            )

        return actions

    @executeskart
    def showLog(self):
        dialog = HistoryDialog(self.repo, self.layername)
        dialog.exec()

    def addToProject(self):
        layer = self.repo.workingCopyLayer(self.layername)
        if layer is None:
            iface.messageBar().pushMessage(
                "Add layer",
                "Layer could not be added\nOnly Gpkg-based repositories are supported",
                level=Qgis.Warning,
            )
        else:
            QgsProject.instance().addMapLayer(layer)

    @executeskart
    def removeFromRepo(self):
        name = os.path.basename(self.repo.path)
        path = os.path.join(self.repo.path, f"{name}.gpkg|layername={self.layername}")
        layer = layerFromSource(path)
        if layer:
            msg = (
                "The layer is loaded in QGIS. \n"
                "It will be removed from the repository and from your current project.\n"
                "Do you want to continue?"
            )
        else:
            msg = (
                "The layer will be removed from the repository.\n"
                "Do you want to continue?"
            )

        ret = QMessageBox.warning(
            iface.mainWindow(), "Remove layer", msg, QMessageBox.Yes | QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            self.repo.deleteLayer(self.layername)
            iface.messageBar().pushMessage(
                "Remove layer",
                "Layer correctly removed",
                level=Qgis.Info,
            )
            if layer:
                QgsProject.instance().removeMapLayers([layer.id()])
                iface.mapCanvas().refresh()

    @executeskart
    def commitChanges(self):
        if self.repo.isMerging():
            iface.messageBar().pushMessage(
                "Commit",
                "Cannot commit if repository while repository is in merging status",
                level=Qgis.Warning,
            )
        else:
            changes = self.repo.changes().get(self.layername, {})
            if changes:
                msg, ok = QInputDialog.getMultiLineText(
                    iface.mainWindow(), "Commit", "Enter commit message:"
                )
                if ok and msg:
                    if self.repo.commit(msg):
                        iface.messageBar().pushMessage(
                            "Commit", "Changes correctly committed", level=Qgis.Info
                        )
                    else:
                        iface.messageBar().pushMessage(
                            "Commit",
                            "Changes could not be commited",
                            level=Qgis.Warning,
                        )
            else:
                iface.messageBar().pushMessage(
                    "Commit", "Nothing to commit", level=Qgis.Warning
                )
