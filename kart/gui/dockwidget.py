import math
import os
import re
import tempfile
from functools import partial

from qgis.core import (
    Qgis,
    QgsMimeDataUtils,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.gui import QgsDockWidget
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt import uic
from qgis.PyQt.QtCore import (
    QByteArray,
    QDataStream,
    QEvent,
    QIODevice,
    QMimeData,
    Qt,
)
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QAction,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTreeWidgetItem,
    QVBoxLayout,
)
from qgis.utils import iface
from qgis.core import QgsApplication

from kart.core import RepoManager
from kart.gui import icons
from kart.gui.clonedialog import CloneDialog
from kart.gui.conflictsdialog import ConflictsDialog
from kart.gui.dbconnectiondialog import DbConnectionDialog
from kart.gui.diffviewer import DiffViewerDialog
from kart.gui.historyviewer import HistoryDialog
from kart.gui.initdialog import InitDialog
from kart.gui.mergedialog import MergeDialog
from kart.gui.pulldialog import PullDialog
from kart.gui.pushdialog import PushDialog
from kart.gui.repopropertiesdialog import RepoPropertiesDialog
from kart.gui.switchdialog import SwitchDialog
from kart.kartapi import (
    KartException,
    Repository,
    checkKartInstalled,
    executeskart,
)
from kart.utils import (
    AUTO_COMMIT_ON_SAVE,
    AUTO_PUSH,
    LASTREPO,
    WARN_ON_EXIT_UNCOMMITTED,
    WARN_ON_EXIT_UNPUSHED,
    confirm,
    layerFromSource,
    progressBar,
    setSetting,
    setting,
    tr,
    waitcursor,
)

pluginPath = os.path.split(os.path.dirname(__file__))[0]

PROJECT_MARKER_PREFIX = "kart_plugin_loaded_qgs"


def project_tracking_keys():
    return (
        f"{PROJECT_MARKER_PREFIX}_repo_path",
        f"{PROJECT_MARKER_PREFIX}_rel_path",
        f"{PROJECT_MARKER_PREFIX}_blob_hash",
    )


WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "dockwidget.ui"))


class KartDockWidget(QgsDockWidget, WIDGET):
    def __init__(self):
        super().__init__(iface.mainWindow())
        self.setupUi(self)

        self.retranslateUi()

        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.customContextMenuRequested.connect(self.showPopupMenu)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

        def onItemExpanded(item):
            if hasattr(item, "onExpanded"):
                item.onExpanded()

        self.tree.itemExpanded.connect(onItemExpanded)

        def onItemDoubleClicked(item, column):
            if isinstance(item, DatasetItem):
                item.addToProject()

        self.tree.itemDoubleClicked.connect(onItemDoubleClicked)

        def mimeTypes():
            return ["application/x-vnd.qgis.qgis.uri"]

        def mimeData(items):
            mimeData = QMimeData()
            encodedData = QByteArray()
            stream = QDataStream(encodedData, QIODevice.OpenModeFlag.WriteOnly)

            for item in items:
                if isinstance(item, DatasetItem):
                    layer = item.repo.workingCopyLayer(item.name)
                    uri = QgsMimeDataUtils.Uri(layer)
                    stream.writeQString(uri.data())

            mimeData.setData("application/x-vnd.qgis.qgis.uri", encodedData)
            return mimeData

        def dropMimeData(parent, index, data, action):
            return False

        self.tree.mimeData = mimeData
        self.tree.mimeTypes = mimeTypes
        self.tree.dropMimeData = dropMimeData

        self.fillTree()

        self.btnSaveProjectToKart = QPushButton(tr("Save project to Kart"), self)
        self.btnSaveProjectToKart.setToolTip(
            tr("Save the current dirty QGIS project as a diffable .qgs file in Kart")
        )
        self.btnSaveProjectToKart.clicked.connect(self.saveProjectToKartFromButton)
        self.verticalLayout.insertWidget(1, self.btnSaveProjectToKart)
        self.tree.currentItemChanged.connect(lambda *args: self.updateSaveProjectButton())
        self._installProjectDirtyHooks()
        self._installSaveShortcutFilter()
        self.updateSaveProjectButton()

    def fillTree(self):
        self.tree.clear()
        self.reposItem = ReposItem()
        self.tree.addTopLevelItem(self.reposItem)
        self.reposItem.setExpanded(True)
        if checkKartInstalled(False):
            lastRepo = setting(LASTREPO)
            for i in range(self.reposItem.childCount()):
                item = self.reposItem.child(i)
                if item.repo.path == lastRepo:
                    item.populate()
                    item.setExpanded(True)
                    item.datasetsItem.setExpanded(True)

    def showPopupMenu(self, point):
        item = self.tree.currentItem()
        if item is not None:
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

    def retranslateUi(self, *args):
        """Update translations for UI elements from the .ui file"""
        super().retranslateUi(self)

        self.setWindowTitle(tr("Kart repositories"))
        self.label_2.setText(tr("Tip: right-click on items for available actions"))

    def updateSaveProjectButton(self):
        project = QgsProject.instance()
        info = self._activeProjectInfo()
        self.btnSaveProjectToKart.setVisible(info is not None)
        self.btnSaveProjectToKart.setEnabled(info is not None and project.isDirty())

    def saveProjectToKartFromButton(self):
        repo_item = self._repoItemForActiveProject()
        if repo_item is not None:
            repo_item.saveProjectToRepo()

    def _installProjectDirtyHooks(self):
        project = QgsProject.instance()
        for signal_name in ("isDirtyChanged", "readProject", "cleared"):
            signal = getattr(project, signal_name, None)
            if signal is None:
                continue
            try:
                signal.connect(lambda *args: self.updateSaveProjectButton())
            except Exception:
                pass
        readProject = getattr(project, "readProject", None)
        if readProject is not None:
            try:
                readProject.connect(self._onProjectRead)
            except Exception:
                pass
        cleared = getattr(project, "cleared", None)
        if cleared is not None:
            try:
                cleared.connect(self._onProjectCleared)
            except Exception:
                pass
        projectSaved = getattr(project, "projectSaved", None)
        if projectSaved is not None:
            try:
                projectSaved.connect(self._onProjectSaved)
            except Exception:
                pass
        isDirtyChanged = getattr(project, "isDirtyChanged", None)
        if isDirtyChanged is not None:
            try:
                isDirtyChanged.connect(self._onProjectDirtyChanged)
            except Exception:
                pass

    def _onProjectCleared(self, *args):
        project = QgsProject.instance()
        repo_key, path_key, hash_key = project_tracking_keys()
        for key in (repo_key, path_key, hash_key):
            try:
                project.setProperty(key, None)
            except Exception:
                pass
        self.updateSaveProjectButton()

    def _onProjectDirtyChanged(self, *args):
        repo_item = self._repoItemForActiveProject() or self._currentRepoItem()
        if repo_item is None:
            return
        try:
            if hasattr(repo_item, "filesItem") and repo_item.filesItem is not None:
                repo_item.filesItem.refreshContent()
            repo_item.setTitle()
        except Exception:
            pass

    def _onProjectSaved(self, *args):
        repo_item = self._repoItemForActiveProject()
        if repo_item is None:
            return
        try:
            if hasattr(repo_item, "filesItem") and repo_item.filesItem is not None:
                repo_item.filesItem.refreshContent()
        except Exception:
            pass

    def _onProjectRead(self, *args):
        """Auto-detect .qgs files opened from a Kart working copy."""
        project = QgsProject.instance()
        project_path = project.fileName()
        if not project_path:
            return
        for i in range(self.reposItem.childCount() if hasattr(self, "reposItem") else 0):
            item = self.reposItem.child(i)
            if not isinstance(item, RepoItem):
                continue
            if item.repo.pathInsideRepo(project_path):
                rel_path = item.repo.repoRelativePath(project_path)
                self._setLoadedProjectMarker(item.repo.path, rel_path)
                self.updateSaveProjectButton()
                return

    def _installSaveShortcutFilter(self):
        try:
            from qgis.utils import iface as _iface
            main_win = _iface.mainWindow()
            if main_win is not None:
                main_win.installEventFilter(self)
        except Exception:
            pass

    def cleanup(self):
        try:
            from qgis.utils import iface as _iface
            main_win = _iface.mainWindow()
            if main_win is not None:
                main_win.removeEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Close and obj is iface.mainWindow():
            self._onMainWindowClose()
        if (
            event.type() == QEvent.KeyPress
            and setting(AUTO_COMMIT_ON_SAVE)
        ):
            from qgis.PyQt.QtCore import Qt as _Qt
            key = event.key()
            mods = event.modifiers()
            if key == _Qt.Key_S and (mods & _Qt.ControlModifier):
                repo_item = self._repoItemForProjectSave()
                if repo_item is not None:
                    event.accept()
                    repo_item.saveProjectToRepo()
                    return True
        return super().eventFilter(obj, event)

    def _onMainWindowClose(self):
        """Prompt on exit for unsaved QGIS project changes and uncommitted Kart changes."""
        # 1. Unsaved QGIS project tracked in Kart
        project = QgsProject.instance()
        if project.isDirty():
            info = self._activeProjectInfo()
            if info:
                repo_path, rel_path, _blob_hash = info
                repo_item = self._repoItemForPath(repo_path)
                if repo_item is not None:
                    reply = QMessageBox.question(
                        iface.mainWindow(),
                        tr("Save QGIS project to Kart"),
                        tr(
                            "The QGIS project '{rel_path}' has unsaved changes and is tracked in a "
                            "Kart repository.\n\nSave it to the Kart repository before quitting?"
                        ).format(rel_path=rel_path),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        try:
                            repo_item.saveProjectToRepo()
                        except Exception:
                            pass

        # 2. Uncommitted or unpushed Kart changes
        warn_uncommitted = setting(WARN_ON_EXIT_UNCOMMITTED)
        warn_unpushed = setting(WARN_ON_EXIT_UNPUSHED)
        if not warn_uncommitted and not warn_unpushed:
            return
        if not hasattr(self, "reposItem"):
            return
        uncommitted_repos = []
        unpushed_repos = []
        for i in range(self.reposItem.childCount()):
            item = self.reposItem.child(i)
            if not isinstance(item, RepoItem):
                continue
            try:
                is_clean = item.repo.isWorkingTreeClean()
                if warn_uncommitted and not is_clean:
                    uncommitted_repos.append(item.repo.title() or os.path.normpath(item.repo.path))
                if warn_unpushed:
                    ahead, _ = item.repo.aheadBehind()
                    if ahead:
                        unpushed_repos.append(item.repo.title() or os.path.normpath(item.repo.path))
            except Exception:
                pass
        if not uncommitted_repos and not unpushed_repos:
            return
        parts = []
        if uncommitted_repos:
            names = "\n".join(f"  • {r}" for r in uncommitted_repos)
            parts.append(f"Uncommitted changes:\n{names}")
        if unpushed_repos:
            names = "\n".join(f"  • {r}" for r in unpushed_repos)
            parts.append(f"Unpushed commits:\n{names}")
        QMessageBox.warning(
            iface.mainWindow(),
            tr("Unsynchronised Kart changes"),
            "\n\n".join(parts) + "\n\n" + tr("Make sure to commit and push before quitting."),
        )

    def _activeProjectInfo(self):
        repo_key, path_key, hash_key = project_tracking_keys()
        project = QgsProject.instance()
        repo_path = project.readEntry(repo_key, "/")[0] or None
        rel_path = project.readEntry(path_key, "/")[0] or None
        blob_hash = project.readEntry(hash_key, "/")[0] or None
        if repo_path and rel_path:
            return repo_path, rel_path, blob_hash
        return None

    def _repoItemForPath(self, repo_path):
        if not hasattr(self, "reposItem"):
            return None
        for i in range(self.reposItem.childCount()):
            item = self.reposItem.child(i)
            if isinstance(item, RepoItem) and os.path.normpath(item.repo.path) == os.path.normpath(repo_path):
                return item
        return None

    def _repoItemForActiveProject(self):
        info = self._activeProjectInfo()
        if info is None:
            return None
        return self._repoItemForPath(info[0])

    def _currentRepoItem(self):
        item = self.tree.currentItem()
        while item is not None:
            if isinstance(item, RepoItem):
                return item
            item = item.parent()
        return None

    def _repoItemForProjectSave(self):
        project = QgsProject.instance()
        if not project.isDirty():
            return None
        repo_item = self._repoItemForActiveProject()
        if repo_item is not None:
            return repo_item
        project_path = project.fileName()
        if not project_path:
            return None
        if not hasattr(self, "reposItem"):
            return None
        for i in range(self.reposItem.childCount()):
            item = self.reposItem.child(i)
            if isinstance(item, RepoItem) and item.repo.pathInsideRepo(project_path):
                return item
        return None

    def _setLoadedProjectMarker(self, repo_path, rel_path):
        project = QgsProject.instance()
        repo_key, path_key, hash_key = project_tracking_keys()
        project.writeEntry(repo_key, "/", repo_path)
        project.writeEntry(path_key, "/", rel_path)
        try:
            blob_hash = Repository(repo_path).blobHash(rel_path)
            project.writeEntry(hash_key, "/", blob_hash)
        except Exception:
            project.writeEntry(hash_key, "/", "")

    def _activeProjectMarker(self):
        return self._activeProjectInfo()

    def _showTextDialog(self, title, text):
        dlg = QDialog(iface.mainWindow())
        dlg.setWindowTitle(title)
        layout = QVBoxLayout(dlg)
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(text)
        edit.setMinimumSize(700, 500)
        layout.addWidget(edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()

    def _confirmProjectSave(self, rel_path, diff_text, default_message):
        dlg = QDialog(iface.mainWindow())
        dlg.setWindowTitle(tr("Save project to Kart"))
        layout = QVBoxLayout(dlg)
        if diff_text:
            edit = QTextEdit()
            edit.setReadOnly(True)
            edit.setPlainText(diff_text)
            edit.setMinimumSize(700, 400)
            layout.addWidget(edit)
        from qgis.PyQt.QtWidgets import QLineEdit
        msg_edit = QLineEdit(default_message)
        layout.addWidget(msg_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return msg_edit.text(), True
        return "", False

    def _autoPushForRepo(self, repo_item):
        if not setting(AUTO_PUSH):
            return
        try:
            remotes = repo_item.repo.remotes()
            if not remotes:
                return
            remote = next(iter(remotes))
            branch = repo_item.repo.currentBranch()
            repo_item.repo.push(remote, branch)
        except Exception:
            pass


class RefreshableItem(QTreeWidgetItem):
    def actions(self):
        actions = [
            (tr("Refresh"), self.refreshContent, icons.refreshIcon),
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

        self.setText(0, tr("Repositories"))
        self.setIcon(0, icons.repoIcon)
        self.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

        self.populate()

        RepoManager.instance().repo_added.connect(self.addRepoToUI)

    def populate(self):
        for repo in RepoManager.instance().repos():
            item = RepoItem(repo)
            self.addChild(item)

    def _actions(self):
        actions = [
            (tr("Add existing repository..."), self.addRepo, icons.addRepoIcon),
            (tr("Create new repository..."), self.createRepo, icons.createRepoIcon),
            (tr("Clone repository..."), self.cloneRepo, icons.cloneRepoIcon),
        ]

        return actions

    def addRepo(self):
        folder = QFileDialog.getExistingDirectory(iface.mainWindow(), tr("Repository Folder"), "")
        if folder:
            repo = Repository(folder)
            if repo.isInitialized():
                RepoManager.instance().add_repo(repo)
            else:
                iface.messageBar().pushMessage(
                    tr("Error"),
                    tr("The selected folder is not a Kart repository"),
                    level=Qgis.MessageLevel.Warning,
                )

    @executeskart
    def createRepo(self):
        dialog = InitDialog()
        ret = dialog.exec()
        if ret == QDialog.DialogCode.Accepted:
            if os.path.exists(dialog.folder):
                if any(os.scandir(dialog.folder)):
                    iface.messageBar().pushMessage(
                        tr("Error"),
                        tr("The specified folder is not empty"),
                        level=Qgis.MessageLevel.Warning,
                    )
                    return
            else:
                try:
                    os.makedirs(dialog.folder)
                except Exception:
                    iface.messageBar().pushMessage(
                        tr("Error"),
                        tr("Could not create the specified folder"),
                        level=Qgis.MessageLevel.Warning,
                    )
                    return
            repo = Repository(dialog.folder)
            repo.init(dialog.location)
            if repo.isInitialized():
                RepoManager.instance().add_repo(repo)
            else:
                iface.messageBar().pushMessage(
                    tr("Error"),
                    tr("Could not initialize repository"),
                    level=Qgis.MessageLevel.Warning,
                )

    @executeskart
    def cloneRepo(self):
        def _processProgressLine(bar, line):
            if "Writing dataset" in line:
                datasetname = line.split(":")[-1].strip()
                bar.setText(tr(f"Checking out layer '{datasetname}'"))
            elif line.startswith("Receiving objects: ") or line.startswith("Writing objects: "):
                tokens = line.split(": ")
                bar.setText(tokens[0])
                bar.setValue(math.floor(float(tokens[1][1 : tokens[1].find("%")].strip())))
            else:
                msg = line.split(" - ")[-1]
                if "%" in msg:
                    matches = re.findall(r"(\d+(\.\d+)?)", msg)
                    if matches:
                        value = math.floor(float(matches[0][0]))
                        bar.setValue(value)

        dialog = CloneDialog()
        dialog.show()
        ret = dialog.exec()
        if ret == QDialog.DialogCode.Accepted:
            with progressBar("Clone") as bar:
                bar.setText(tr("Cloning repository"))
                repo = Repository.clone(
                    src=dialog.src,
                    dst=dialog.dst,
                    location=dialog.location,
                    extent=dialog.extent,
                    username=dialog.username,
                    password=dialog.password,
                    output_handler=partial(_processProgressLine, bar),
                )
            RepoManager.instance().add_repo(repo)

    def addRepoToUI(self, repo: Repository):
        item = RepoItem(repo)
        self.addChild(item)
        item.setExpanded(True)


class RepoItem(RefreshableItem):
    def __init__(self, repo):
        QTreeWidgetItem.__init__(self)
        self.repo = repo

        self.populated = False
        self.filesItem = None

        self.setTitle()
        self.setIcon(0, icons.repoIcon)
        self.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

    def refreshContent(self):
        self.takeChildren()
        self.populate()
        self.setTitle()

    def setTitle(self):
        if self.populated:
            try:
                title = (
                    f"{self.repo.title() or os.path.normpath(self.repo.path)} "
                    f"[{self.repo.currentBranch()}]"
                )
            except KartException:
                title = f"{self.repo.title() or os.path.normpath(self.repo.path)}"
        else:
            title = f"{self.repo.title() or os.path.normpath(self.repo.path)}"
        self.setText(0, title)

    def onExpanded(self):
        if not self.populated:
            self.populate()

    def populate(self):
        self.datasetsItem = DatasetsItem(self.repo)
        self.addChild(self.datasetsItem)
        setSetting(LASTREPO, self.repo.path)
        self.populated = True
        self.datasetsItem.setExpanded(True)
        self.filesItem = FilesItem(self.repo)
        self.addChild(self.filesItem)
        self.setTitle()

    def actions(self):
        actions = []

        if self.repo.isMerging():
            actions.extend(
                [
                    (
                        tr("Resolve conflicts..."),
                        self.resolveConflicts,
                        icons.resolveIcon,
                    ),
                    (tr("Continue merge"), self.continueMerge, icons.mergeIcon),
                    (tr("Abort merge"), self.abortMerge, icons.abortIcon),
                ]
            )
        else:
            actions.extend(
                [
                    (tr("Show log..."), self.showLog, icons.logIcon),
                    (
                        tr("Show working copy changes..."),
                        self.showChanges,
                        icons.diffIcon,
                    ),
                    (
                        tr("Discard working copy changes"),
                        self.discardChanges,
                        icons.discardIcon,
                    ),
                    (
                        tr("Commit working copy changes..."),
                        self.commitChanges,
                        icons.commitIcon,
                    ),
                    (tr("Switch branch..."), self.switchBranch, icons.checkoutIcon),
                    (
                        tr("Merge into current branch..."),
                        self.mergeBranch,
                        icons.mergeIcon,
                    ),
                    ("divider", None, None),
                    (tr("Pull..."), self.pull, icons.pullIcon),
                    (tr("Push..."), self.push, icons.pushIcon),
                    ("divider", None, None),
                    (
                        tr("Import dataset from file..."),
                        self.importLayerFromFile,
                        icons.importIcon,
                    ),
                    (
                        tr("Import dataset from database..."),
                        self.importLayerFromDatabase,
                        icons.importIcon,
                    ),
                    (tr("Apply patch..."), self.applyPatch, icons.patchIcon),
                ]
            )

        actions.extend(
            [
                ("divider", None, None),
                (tr("Refresh"), self.refreshContent, icons.refreshIcon),
                (tr("Properties..."), self.showProperties, icons.propertiesIcon),
                (tr("Remove this repository"), self.removeRepository, icons.removeIcon),
            ]
        )

        return actions

    def showProperties(self):
        dialog = RepoPropertiesDialog(self.repo)
        dialog.show()
        dialog.exec()
        self.setTitle()

    def removeRepository(self):
        if confirm(tr("Are you sure you want to remove this repository?")):
            self.parent().takeChild(self.parent().indexOfChild(self))
            RepoManager.instance().remove_repo(self.repo)

    @executeskart
    def showLog(self):
        dialog = HistoryDialog(self.repo)
        dialog.exec()
        self.refreshContent()

    def importLayerFromDatabase(self):
        dlg = DbConnectionDialog()
        ret = dlg.exec()
        if ret == QDialog.DialogCode.Accepted:
            self._importIntoRepo(dlg.url)

    def importLayerFromFile(self):
        filepath, _ = QFileDialog.getOpenFileName(
            iface.mainWindow(), tr("Select vector layer to import"), "", "*.*"
        )
        if filepath:
            if os.path.splitext(filepath)[-1].lower() not in [".gpkg", ".shp"]:
                self._exportToGpkgAndImportIntoRepo(filepath)
            else:
                self._importIntoRepo(filepath)

    @waitcursor
    def _exportToGpkgAndImportIntoRepo(self, filepath):
        layer = QgsVectorLayer(filepath, "", "ogr")
        if not layer.isValid():
            iface.messageBar().pushMessage(
                tr("Import"),
                tr("The selected file is not a valid vector layer"),
                level=Qgis.MessageLevel.Warning,
            )
            return
        tmpfolder = tempfile.TemporaryDirectory()
        filename = os.path.splitext(os.path.basename(filepath))[0]
        filenameToImport = os.path.join(tmpfolder.name, f"{filename}.gpkg")
        ret = QgsVectorFileWriter.writeAsVectorFormat(
            layer, filenameToImport, "utf-8", layer.crs()
        )
        if ret[0] != QgsVectorFileWriter.WriterError.NoError:
            iface.messageBar().pushMessage(
                tr("Import"),
                tr("Could not convert the selected layer to a gpkg file"),
                level=Qgis.MessageLevel.Warning,
            )
        else:
            self._importIntoRepo(filenameToImport)
            tmpfolder.cleanup()

    @executeskart
    def _importIntoRepo(self, source):
        self.repo.importIntoRepo(source)
        iface.messageBar().pushMessage(
            tr("Import"), tr("Layer correctly imported"), level=Qgis.MessageLevel.Info
        )
        if self.populated:
            self.datasetsItem.refreshContent()
        self.setTitle()  # Update title to add branch name in case of first commit

    @executeskart
    def commitChanges(self):
        if self.repo.isWorkingTreeClean():
            iface.messageBar().pushMessage(
                tr("Commit"), tr("Nothing to commit"), level=Qgis.MessageLevel.Warning
            )
        else:
            msg, ok = QInputDialog.getMultiLineText(
                iface.mainWindow(), tr("Commit"), tr("Enter commit message:")
            )
            if ok and msg:
                if self.repo.commit(msg):
                    iface.messageBar().pushMessage(
                        tr("Commit"),
                        tr("Changes correctly committed"),
                        level=Qgis.MessageLevel.Info,
                    )
                    self._autoPush()
                else:
                    iface.messageBar().pushMessage(
                        tr("Commit"),
                        tr("Changes could not be commited"),
                        level=Qgis.MessageLevel.Warning,
                    )

    def _autoPush(self):
        if not setting(AUTO_PUSH):
            return
        try:
            remotes = self.repo.remotes()
            if not remotes:
                return
            remote = next(iter(remotes))
            branch = self.repo.currentBranch()
            self.repo.push(remote, branch)
        except Exception:
            pass

    def saveProjectToRepo(self):
        project = QgsProject.instance()
        info = self.treeWidget().parent()._activeProjectInfo() if self.treeWidget() and self.treeWidget().parent() else None
        # Fallback: look up from dock
        dock = self._getDock()
        if dock is None:
            return
        info = dock._activeProjectInfo()
        if info is None:
            return
        repo_path, rel_path, old_hash = info
        import tempfile as _tf
        tmp = _tf.NamedTemporaryFile(suffix=".qgs", delete=False)
        tmp.close()
        try:
            project.write(tmp.name)
            diff = self.repo.diffFileAgainstPath(rel_path, tmp.name)
        except Exception:
            diff = ""
        finally:
            pass
        msg, ok = dock._confirmProjectSave(rel_path, diff, f"Update {rel_path}")
        if not ok:
            return
        try:
            self.repo.commitFiles(msg, {rel_path: tmp.name})
            import os as _os
            _os.unlink(tmp.name)
            new_hash = self.repo.blobHash(rel_path)
            dock._setLoadedProjectMarker(self.repo.path, rel_path)
            dock.updateSaveProjectButton()
            if hasattr(self, "filesItem") and self.filesItem is not None:
                self.filesItem.refreshContent()
            self.setTitle()
            dock._autoPushForRepo(self)
        except Exception as e:
            iface.messageBar().pushMessage(tr("Error"), str(e), level=Qgis.MessageLevel.Warning)

    def _getDock(self):
        w = self.treeWidget()
        if w is None:
            return None
        p = w.parent()
        while p is not None:
            if isinstance(p, KartDockWidget):
                return p
            p = p.parent() if hasattr(p, "parent") and callable(p.parent) else None
        return None

    @executeskart
    def showChanges(self):
        hasSchemaChanges = self.repo.diffHasSchemaChanges()
        if hasSchemaChanges:
            iface.messageBar().pushMessage(
                tr("Changes"),
                tr("There are schema changes in the working copy and changes cannot be shown"),
                level=Qgis.MessageLevel.Warning,
            )
            return
        diff = self.repo.diff()
        hasChanges = any([bool(c) for c in diff.values()])
        if hasChanges:
            dialog = DiffViewerDialog(
                iface.mainWindow(), diff, self.repo, showRecoverNewButton=False
            )
            dialog.exec()
        else:
            iface.messageBar().pushMessage(
                tr("Changes"),
                tr("There are no changes in the working copy"),
                level=Qgis.MessageLevel.Warning,
            )

    @executeskart
    def switchBranch(self):
        dialog = SwitchDialog(self.repo)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repo.checkoutBranch(dialog.branch, dialog.force)
            self.setTitle()

    @executeskart
    def mergeBranch(self):
        dialog = MergeDialog(self.repo)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            conflicts = self.repo.mergeBranch(
                dialog.ref, msg=dialog.message, noff=dialog.noff, ffonly=dialog.ffonly
            )
            if conflicts:
                QMessageBox.warning(
                    iface.mainWindow(),
                    tr("Merge"),
                    tr(
                        "There were conflicts during the merge operation.\n"
                        "Resolve them and then commit your changes to \n"
                        "complete the merge."
                    ),
                )
            else:
                iface.messageBar().pushMessage(
                    tr("Merge"),
                    tr("Branch correctly merged"),
                    level=Qgis.MessageLevel.Info,
                )

    @executeskart
    def discardChanges(self):
        if confirm(tr("Are you sure you want to discard the working copy changes?")):
            self.repo.restore("HEAD")
            iface.messageBar().pushMessage(
                tr("Discard changes"),
                tr("Working copy changes have been discarded"),
                level=Qgis.MessageLevel.Info,
            )

    @executeskart
    def continueMerge(self):
        if self.repo.conflicts():
            iface.messageBar().pushMessage(
                tr("Merge"),
                tr("Cannot continue. There are merge conflicts."),
                level=Qgis.MessageLevel.Warning,
            )
        else:
            self.repo.continueMerge()
            iface.messageBar().pushMessage(
                tr("Merge"),
                tr("Merge operation was correctly continued and closed"),
                level=Qgis.MessageLevel.Info,
            )

    @executeskart
    def abortMerge(self):
        self.repo.abortMerge()
        iface.messageBar().pushMessage(
            tr("Merge"),
            tr("Merge operation was correctly aborted"),
            level=Qgis.MessageLevel.Info,
        )

    @executeskart
    def resolveConflicts(self):
        if self.repo.conflictsHaveSchemaChanges():
            iface.messageBar().pushMessage(
                tr("Resolve"),
                tr(
                    "Conflicts involve schema changes and cannot be resolved "
                    "using the plugin interface"
                ),
                level=Qgis.MessageLevel.Warning,
            )
            return
        conflicts = self.repo.conflicts()
        if conflicts:
            dialog = ConflictsDialog(conflicts)
            dialog.exec()
            if dialog.okToMerge:
                self.repo.resolveConflicts(dialog.resolvedFeatures)
                self.repo.continueMerge()
                iface.messageBar().pushMessage(
                    tr("Merge"),
                    tr("Merge operation was correctly continued and closed"),
                    level=Qgis.MessageLevel.Info,
                )
        else:
            iface.messageBar().pushMessage(
                tr("Resolve"),
                tr("There are no conflicts to resolve"),
                level=Qgis.MessageLevel.Warning,
            )

    @executeskart
    def push(self):
        dialog = PushDialog(self.repo)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repo.push(dialog.remote, dialog.branch, dialog.pushAll)

            if dialog.pushAll:
                template = tr("Repo changes have been pushed to all branches at {remote}")
                hint_text = template.format(remote=dialog.remote)
            else:
                template = tr("Repo changes have been pushed to {remote}/{branch}")
                hint_text = template.format(remote=dialog.remote, branch=dialog.branch)

            iface.messageBar().pushMessage(
                tr("Push"),
                hint_text,
                level=Qgis.MessageLevel.Info,
            )

    @executeskart
    def pull(self):
        dialog = PullDialog(self.repo)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            ret = self.repo.pull(dialog.remote, dialog.branch)
            if not ret:
                QMessageBox.warning(
                    iface.mainWindow(),
                    tr("Pull"),
                    tr(
                        "There were conflicts during the pull operation.\n"
                        "Resolve them and then commit your changes to \n"
                        "complete it."
                    ),
                )
            else:
                iface.messageBar().pushMessage(
                    tr("Pull"),
                    tr("Pull correctly performed"),
                    level=Qgis.MessageLevel.Info,
                )

    @executeskart
    def applyPatch(self):
        filename, _ = QFileDialog.getOpenFileName(
            iface.mainWindow(),
            tr("Patch file"),
            "",
            tr("Patch files (*.patch);;All files (*.*)"),
        )
        if filename:
            self.repo.applyPatch(filename)
            iface.messageBar().pushMessage(
                tr("Apply patch"),
                tr("Patch was correctly applied to working copy"),
                level=Qgis.MessageLevel.Info,
            )


class DatasetsItem(RefreshableItem):
    def __init__(self, repo):
        QTreeWidgetItem.__init__(self)

        self.repo = repo

        self.setText(0, tr("Datasets"))
        self.setIcon(0, icons.datasetIcon)

        self.populate()

    @executeskart
    def populate(self):
        vectorDatasets, tables = self.repo.datasets()
        for dataset in vectorDatasets:
            item = DatasetItem(dataset, self.repo, False)
            self.addChild(item)
        for table in tables:
            item = DatasetItem(table, self.repo, True)
            self.addChild(item)

    def _actions(self):
        return []


class DatasetItem(QTreeWidgetItem):
    def __init__(self, name, repo, isTable):
        QTreeWidgetItem.__init__(self)
        self.name = name
        self.repo = repo
        self.isTable = isTable

        self.setText(0, name)
        self.setIcon(0, icons.tableIcon if isTable else icons.vectorDatasetIcon)

    def actions(self):
        actions = [(tr("Add to QGIS project"), self.addToProject, icons.addtoQgisIcon)]
        if not self.repo.isMerging():
            actions.extend(
                [
                    ("divider", None, None),
                    (tr("Show log..."), self.showLog, icons.logIcon),
                    (
                        tr("Show working copy changes for this dataset..."),
                        self.showChanges,
                        icons.diffIcon,
                    ),
                    (
                        tr("Discard working copy changes for this dataset"),
                        self.discardChanges,
                        icons.discardIcon,
                    ),
                    (
                        tr("Commit working copy changes for this dataset..."),
                        self.commitChanges,
                        icons.commitIcon,
                    ),
                    ("divider", None, None),
                    (
                        tr("Remove from repository"),
                        self.removeFromRepo,
                        icons.removeIcon,
                    ),
                ]
            )

        return actions

    @executeskart
    def commitChanges(self):
        changes = self.repo.changes().get(self.name)
        if changes is None:
            iface.messageBar().pushMessage(
                tr("Commit"), tr("Nothing to commit"), level=Qgis.MessageLevel.Warning
            )
        else:
            msg, ok = QInputDialog.getMultiLineText(
                iface.mainWindow(), tr("Commit"), tr("Enter commit message:")
            )
            if ok and msg:
                if self.repo.commit(msg, dataset=self.name):
                    iface.messageBar().pushMessage(
                        tr("Commit"),
                        tr("Changes correctly committed"),
                        level=Qgis.MessageLevel.Info,
                    )
                else:
                    iface.messageBar().pushMessage(
                        tr("Commit"),
                        tr("Changes could not be commited"),
                        level=Qgis.MessageLevel.Warning,
                    )

    @executeskart
    def showChanges(self):
        hasSchemaChanges = self.repo.diffHasSchemaChanges(dataset=self.name)
        if hasSchemaChanges:
            iface.messageBar().pushMessage(
                tr("Changes"),
                tr("There are schema changes in the working copy and changes cannot be shown"),
                level=Qgis.MessageLevel.Warning,
            )
            return
        diff = self.repo.diff(dataset=self.name)
        if diff.get(self.name):
            dialog = DiffViewerDialog(
                iface.mainWindow(), diff, self.repo, showRecoverNewButton=False
            )
            dialog.exec()
        else:
            iface.messageBar().pushMessage(
                tr("Changes"),
                tr("There are no changes in the working copy for this dataset"),
                level=Qgis.MessageLevel.Warning,
            )

    @executeskart
    def discardChanges(self):
        if confirm(
            tr("Are you sure you want to discard the working copy changes for this dataset?")
        ):
            self.repo.restore("HEAD", self.name)
            iface.messageBar().pushMessage(
                tr("Discard changes"),
                tr("Working copy changes have been discarded"),
                level=Qgis.MessageLevel.Info,
            )

    @executeskart
    def showLog(self):
        dialog = HistoryDialog(self.repo, self.name)
        dialog.exec()

    def addToProject(self):
        layer = self.repo.workingCopyLayer(self.name)
        if layer is None:
            iface.messageBar().pushMessage(
                tr("Add layer"),
                tr("Dataset could not be added"),
                level=Qgis.MessageLevel.Warning,
            )
        else:
            QgsProject.instance().addMapLayer(layer)

    @executeskart
    def removeFromRepo(self):
        if not self.repo.isWorkingTreeClean():
            iface.messageBar().pushMessage(
                tr("Remove dataset"),
                tr(
                    "There are pending changes in the working copy. "
                    "Commit them before deleting this dataset"
                ),
                level=Qgis.MessageLevel.Warning,
            )
            return
        source = self.repo.workingCopyLayer(self.name).source()
        layer = layerFromSource(source)
        if layer:
            msg = tr(
                "The dataset is loaded in QGIS. \n"
                "It will be removed from the repository and from your current project.\n"
                "Do you want to continue?"
            )
        else:
            msg = tr("The dataset will be removed from the repository.\nDo you want to continue?")

        ret = QMessageBox.warning(
            iface.mainWindow(),
            tr("Remove dataset"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.repo.deleteDataset(self.name)
            iface.messageBar().pushMessage(
                tr("Remove dataset"),
                tr("Dataset correctly removed"),
                level=Qgis.MessageLevel.Info,
            )
            self.parent().refreshContent()
            if layer:
                QgsProject.instance().removeMapLayers([layer.id()])
                iface.mapCanvas().refresh()


class FilesItem(RefreshableItem):
    def __init__(self, repo):
        super().__init__()
        self.repo = repo
        self.setText(0, tr("Files"))
        self.setIcon(0, icons.fileIcon if hasattr(icons, "fileIcon") else icons.refreshIcon)
        self.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

    def populate(self):
        try:
            status = self.repo.fileStatus()
        except Exception:
            return
        modified = status.get("modified") or []
        untracked = status.get("untracked") or []
        deleted = status.get("deleted") or []

        seen = set()
        for rel_path in modified:
            self.addChild(RepoFileItem(rel_path, self.repo, "modified"))
            seen.add(rel_path)
        for rel_path in untracked:
            self.addChild(RepoFileItem(rel_path, self.repo, "untracked"))
            seen.add(rel_path)
        for rel_path in deleted:
            self.addChild(RepoFileItem(rel_path, self.repo, "deleted"))
            seen.add(rel_path)

        try:
            for rel_path in self.repo.trackedAttachmentFiles():
                if rel_path not in seen:
                    self.addChild(RepoFileItem(rel_path, self.repo, "tracked"))
        except Exception:
            pass

    def _actions(self):
        return []


class RepoFileItem(QTreeWidgetItem):
    def __init__(self, rel_path, repo, status="tracked"):
        super().__init__()
        self.rel_path = rel_path
        self.repo = repo
        self.status = status
        self.setText(0, rel_path)
        self._updateIcon()

    def _updateIcon(self):
        if self.status == "modified":
            self.setForeground(0, QBrush(QColor(200, 100, 0)))
        elif self.status == "untracked":
            self.setForeground(0, QBrush(QColor(0, 150, 0)))
        elif self.status == "deleted":
            self.setForeground(0, QBrush(QColor(200, 0, 0)))

    def onDoubleClicked(self):
        if self.status in ("modified", "untracked"):
            self._showFileDiff()

    def actions(self):
        acts = []
        if self.status == "modified":
            acts += [
                (tr("Show working copy diff"), self._showFileDiff, icons.diffIcon if hasattr(icons, "diffIcon") else icons.refreshIcon),
                (tr("Show last commit diff"), self._showCommitDiff, icons.diffIcon if hasattr(icons, "diffIcon") else icons.refreshIcon),
                (tr("Commit file"), self._commitFile, icons.commitIcon if hasattr(icons, "commitIcon") else icons.refreshIcon),
                (tr("Discard changes"), self._discardChanges, icons.refreshIcon),
            ]
        elif self.status == "untracked":
            acts += [
                (tr("Commit file (add)"), self._commitFile, icons.commitIcon if hasattr(icons, "commitIcon") else icons.refreshIcon),
            ]
        elif self.status == "deleted":
            acts += [
                (tr("Commit deletion"), self._commitFileDeletion, icons.commitIcon if hasattr(icons, "commitIcon") else icons.refreshIcon),
                (tr("Restore file"), self._restoreFile, icons.refreshIcon),
            ]
        acts += [
            (tr("Open in Explorer"), self._openInExplorer, icons.refreshIcon),
        ]
        return acts

    def _showFileDiff(self):
        try:
            diff = self.repo.fileDiff(self.rel_path)
            if not diff:
                diff = tr("(no differences)")
            self._showTextDialog(tr("Working copy diff: {path}").format(path=self.rel_path), diff)
        except Exception as e:
            iface.messageBar().pushMessage(tr("Error"), str(e), level=Qgis.MessageLevel.Warning)

    def _showCommitDiff(self):
        try:
            diff = self.repo.diffFile(self.rel_path)
            if not diff:
                diff = tr("(no differences)")
            self._showTextDialog(tr("Last commit diff: {path}").format(path=self.rel_path), diff)
        except Exception as e:
            iface.messageBar().pushMessage(tr("Error"), str(e), level=Qgis.MessageLevel.Warning)

    def _showTextDialog(self, title, text):
        dlg = QDialog(iface.mainWindow())
        dlg.setWindowTitle(title)
        layout = QVBoxLayout(dlg)
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(text)
        edit.setMinimumSize(700, 500)
        layout.addWidget(edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()

    def _discardChanges(self):
        from kart.utils import confirm
        if confirm(tr("Discard working copy changes to '{path}'?").format(path=self.rel_path)):
            try:
                self.repo.restoreFile(self.rel_path)
                self._refreshAfterFileAction()
            except Exception as e:
                iface.messageBar().pushMessage(tr("Error"), str(e), level=Qgis.MessageLevel.Warning)

    def _restoreFile(self):
        from kart.utils import confirm
        if confirm(tr("Restore deleted file '{path}'?").format(path=self.rel_path)):
            try:
                self.repo.restoreFile(self.rel_path)
                self._refreshAfterFileAction()
            except Exception as e:
                iface.messageBar().pushMessage(tr("Error"), str(e), level=Qgis.MessageLevel.Warning)

    def _commitFile(self):
        msg, ok = QInputDialog.getText(
            iface.mainWindow(),
            tr("Commit message"),
            tr("Enter a commit message for '{path}':").format(path=self.rel_path),
        )
        if ok and msg:
            try:
                self.repo.commitFiles(msg, [self.rel_path])
                self._autoPush()
                self._refreshAfterFileAction()
            except Exception as e:
                iface.messageBar().pushMessage(tr("Error"), str(e), level=Qgis.MessageLevel.Warning)

    def _commitFileDeletion(self):
        msg, ok = QInputDialog.getText(
            iface.mainWindow(),
            tr("Commit message"),
            tr("Enter a commit message for deleting '{path}':").format(path=self.rel_path),
        )
        if ok and msg:
            try:
                self.repo.commitFiles(msg, [self.rel_path])
                self._autoPush()
                self._refreshAfterFileAction()
            except Exception as e:
                iface.messageBar().pushMessage(tr("Error"), str(e), level=Qgis.MessageLevel.Warning)

    def _autoPush(self):
        if not setting(AUTO_PUSH):
            return
        try:
            remotes = self.repo.remotes()
            if not remotes:
                return
            remote = next(iter(remotes))
            branch = self.repo.currentBranch()
            self.repo.push(remote, branch)
        except Exception:
            pass

    def _openInExplorer(self):
        full_path = os.path.join(self.repo.path, self.rel_path.replace("/", os.sep))
        folder = os.path.dirname(full_path)
        if os.path.exists(folder):
            import subprocess as _sp
            _sp.Popen(["explorer", folder])

    def _refreshAfterFileAction(self):
        files_item = self.parent()
        if files_item is not None:
            files_item.refreshContent()
