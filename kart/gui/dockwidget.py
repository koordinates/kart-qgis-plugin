import os

from qgis.PyQt import uic

from qgis.PyQt.QtCore import Qt

from qgis.PyQt.QtGui import QIcon

from qgis.PyQt.QtWidgets import (QDockWidget, QTreeWidgetItem,
                                 QAbstractItemView, QFileDialog, QAction,
                                 QMenu, QInputDialog)

from qgis.utils import iface
from qgis.core import Qgis

from kart.kartapi import repos, addRepo, Repository

from kart.gui.historyviewer import HistoryDialog

pluginPath = os.path.split(os.path.dirname(__file__))[0]


def icon(f):
    return QIcon(os.path.join(pluginPath, "img", f))


repoIcon = icon("database.svg")
addRepoIcon = icon("addrepo.png")
createRepoIcon = icon("createrepo.png")
layerIcon = icon('geometry.svg')
logIcon = icon('log.png')
importIcon = icon('import.png')
checkoutIcon = icon('checkout.png')
commitIcon = icon('commit.png')
resetIcon = icon('reset.png')
layersIcon = icon('layer_group.svg')
mergeIcon = icon("merge.png")
addtoQgisIcon = icon('openinqgis.png')

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'dockwidget.ui'))


class KartDockWidget(BASE, WIDGET):
    def __init__(self):
        super(QDockWidget, self).__init__(iface.mainWindow())
        self.setupUi(self)

        self.tree.setFocusPolicy(Qt.NoFocus)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.customContextMenuRequested.connect(self.showPopupMenu)

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
        menu = QMenu()
        for text in item.actions():
            func, icon = item.actions()[text]
            action = QAction(icon, text, menu)
            action.triggered.connect(func)
            menu.addAction(action)

        return menu


class RefreshableItem(QTreeWidgetItem):
    def refreshContent(self):
        self.takeChildren()
        self.populate()


class ReposItem(RefreshableItem):
    def __init__(self):
        QTreeWidgetItem.__init__(self)

        self.setText(0, "Repositories")
        self.setIcon(0, repoIcon)

        self.populate()

    def populate(self):
        for repo in repos():
            item = RepoItem(repo)
            self.addChild(item)

    def actions(self):
        actions = {
            "Add existing repository...": (self.addRepo, addRepoIcon),
            "Create new repository...": (self.createRepo, createRepoIcon)
        }

        return actions

    def addRepo(self):
        folder = QFileDialog.getExistingDirectory(iface.mainWindow(),
                                                  "Repository Folder", "")
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
                    level=Qgis.Warning)

    def createRepo(self):
        folder = QFileDialog.getExistingDirectory(iface.mainWindow(),
                                                  "Repository Folder", "")
        if folder:
            repo = Repository(folder)
            repo.init()
            if repo.isInitialized():
                item = RepoItem(repo)
                self.addChild(item)
            else:
                iface.messageBar().pushMessage(
                    "Error",
                    "Could not initialize repository",
                    level=Qgis.Warning)


class RepoItem(RefreshableItem):
    def __init__(self, repo):
        QTreeWidgetItem.__init__(self)
        self.repo = repo

        self.setText(0, repo.path)
        self.setIcon(0, repoIcon)

        self.populate()

    def populate(self):
        self.layersItem = LayersItem(self.repo)
        self.addChild(self.layersItem)

    def actions(self):
        actions = {
            "Show log...": (self.showLog, logIcon),
            "Import layer into repo...": (self.importLayer, importIcon),
            "Commit changes...": (self.commitChanges, commitIcon),
            "Switch branch...": (self.switchBranch, checkoutIcon),
            "Merge into current branch...": (self.mergeBranch, mergeIcon),
            "Reset current changes": (self.resetBranch, resetIcon)
        }

        return actions

    def showLog(self):
        dialog = HistoryDialog(self.repo)
        dialog.exec()

    def importLayer(self):
        filename, _ = QFileDialog.getOpenFileName(
            iface.mainWindow(), "Select GPKG file to import", "", "*.gpkg")
        if filename:
            self.repo.importGpkg(filename)
            iface.messageBar().pushMessage("Import",
                                           "Layer correctly imported",
                                           level=Qgis.Info)
            self.layersItem.refresh()

    def commitChanges(self):
        status = self.repo.status()
        if status:
            msg, ok = QInputDialog.getText(iface.mainWindow(), 'Commit',
                                           'Enter commit message:')
            if ok:
                self.repo.commit(msg)
                iface.messageBar().pushMessage("Commit",
                                               "Changes correctly committed",
                                               level=Qgis.Info)
        else:
            iface.messageBar().pushMessage("Commit",
                                           "Nothing to commit",
                                           level=Qgis.Warning)

    def switchBranch(self):
        branches = self.repo.branches()
        branch, ok = QInputDialog.getItem(iface.mainWindow(),
                                          "Branch",
                                          "Select branch to switch to:",
                                          branches,
                                          editable=False)
        if ok:
            self.repo.checkoutBranch(branch)

    def mergeBranch(self):
        branches = self.repo.branches()
        branch, ok = QInputDialog.getItem(
            iface.mainWindow(),
            "Branch",
            "Select branch to merge into current branch:",
            branches,
            editable=False)
        if ok:
            self.repo.mergeBranch(branch)
            iface.messageBar().pushMessage("Merge",
                                           "Branch correctly merged",
                                           level=Qgis.Info)

    def resetBranch(self):
        self.repo.reset()
        iface.messageBar().pushMessage("Reset",
                                       "Repository correctly resete",
                                       level=Qgis.Info)


class LayersItem(RefreshableItem):
    def __init__(self, repo):
        QTreeWidgetItem.__init__(self)

        self.repo = repo

        self.setText(0, "Layers")
        self.setIcon(0, layersIcon)

        self.populate()

    def populate(self):

        layers = self.repo.layers()
        for layer in layers:
            item = LayerItem(layer, self.repo)
            self.addChild(item)

    def actions(self):
        return {}


class LayerItem(QTreeWidgetItem):
    def __init__(self, layername, repo):
        QTreeWidgetItem.__init__(self)
        self.layername = layername
        self.repo = repo

        self.setText(0, layername)
        self.setIcon(0, layerIcon)

    def actions(self):
        actions = {
            "Add to QGIS project": (self.addToProject, addtoQgisIcon),
            "Commit changes...": (self.commitChanges, commitIcon)
        }

        return actions

    def addToProject(self):
        name = os.path.basename(self.repo.path)
        path = os.path.join(self.repo.path,
                            f"{name}.gpkg|layername={self.layername}")
        iface.addVectorLayer(path, self.layername, "ogr")

    def commitChanges(self):
        status = self.repo.status().get(self.layername, {})
        if status:
            msg, ok = QInputDialog.getText(iface.mainWindow(), 'Commit',
                                           'Enter commit message:')
            if ok:
                self.repo.commit(msg, self.layername)
        else:
            iface.messageBar().pushMessage("Commit",
                                           "Nothing to commit",
                                           level=Qgis.Warning)
