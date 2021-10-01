import os

from qgis.utils import iface
from qgis.core import Qgis
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QIcon, QFont
from qgis.PyQt.QtWidgets import (
    QDialog,
    QTreeWidgetItem,
    QMessageBox,
    QTableWidgetItem,
    QHeaderView,
    QSizePolicy,
    QTreeWidgetItemIterator,
)

pluginPath = os.path.split(os.path.dirname(__file__))[0]


def icon(f):
    return QIcon(os.path.join(pluginPath, "img", f))


layerIcon = icon("layer.png")
featureIcon = icon("layer.png")

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "conflictsdialog.ui")
)


class ConflictsDialog(BASE, WIDGET):
    def __init__(self, conflicts):
        super(QDialog, self).__init__(iface.mainWindow())
        self.okToMerge = False
        self.conflicts = conflicts
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        self.resize(1024, 768)

        self.resolvedFeatures = {}

        self.tableAttributes.setSortingEnabled(False)
        self.treeConflicts.itemClicked.connect(self.updateFromCurrentSelectedItem)
        self.tableAttributes.cellClicked.connect(self.cellClicked)
        self.btnSolveAllOurs.clicked.connect(self.solveAllOurs)
        self.btnSolveAllTheirs.clicked.connect(self.solveAllTheirs)
        self.btnSolveOurs.clicked.connect(self.solveOurs)
        self.btnSolveTheirs.clicked.connect(self.solveTheirs)
        self.btnSolveFeature.clicked.connect(self.solveFeature)
        self.btnUseModified.clicked.connect(self.solveWithModified)
        self.btnUseAncestor.clicked.connect(self.solveWithAncestor)
        self.btnDeleteFeature.clicked.connect(self.solveWithDeleted)

        self.lastSelectedItem = None

        self.btnSolveOurs.setEnabled(False)
        self.btnSolveTheirs.setEnabled(False)

        self.fillConflictsTree()
        self.treeConflicts.expandToDepth(3)

        self.autoSelectFirstConflict()

    def autoSelectFirstConflict(self):
        iterator = QTreeWidgetItemIterator(self.treeConflicts)
        while iterator.value():
            item = iterator.value()
            if isinstance(item, ConflictItem):
                self.treeConflicts.setCurrentItem(item)
                self.updateFromCurrentSelectedItem()
                return
            iterator += 1

    def fillConflictsTree(self):
        self.treeItems = {}
        for path, conflicts in self.conflicts.items():
            topItem = QTreeWidgetItem()
            topItem.setText(0, path)
            topItem.setIcon(0, layerIcon)
            self.treeConflicts.addTopLevelItem(topItem)
            self.treeItems[path] = {}
            for fid, conflict in conflicts.items():
                conflictItem = ConflictItem(path, fid, conflict)
                topItem.addChild(conflictItem)
                self.treeItems[path][fid] = conflictItem

    def cellClicked(self, row, col):
        if col > 2:
            return
        item = self.tableAttributes.item(row, col)
        finalItem = self.tableAttributes.item(row, 4)
        finalItem.setValue(item.value)

    def updateFromCurrentSelectedItem(self):
        if not self.treeConflicts.selectedItems():
            return
        item = self.treeConflicts.selectedItems()[0]

        self.lastSelectedItem = item
        if isinstance(item, ConflictItem):
            self.currentPath = item.fid
            self.currentLayer = item.path
            self.btnSolveTheirs.setEnabled(True)
            self.btnSolveOurs.setEnabled(True)
            self.btnSolveFeature.setEnabled(True)
            if None in list(item.conflict.values()):
                self.showSolveDeleted()
            else:
                self.showFeatureAttributes()
        else:
            self.stackedWidget.setCurrentWidget(self.pageSolveNormal)
            self.tableAttributes.setRowCount(0)
            self.btnSolveTheirs.setEnabled(False)
            self.btnSolveOurs.setEnabled(False)
            self.btnSolveFeature.setEnabled(False)

    def solveAllOurs(self):
        ret = QMessageBox.warning(
            self,
            "Solve conflicts",
            "Are you sure you want to solve all conflicts using the 'ours' version?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ret == QMessageBox.Yes:
            pass

    def solveAllTheirs(self):
        ret = QMessageBox.warning(
            self,
            "Solve conflicts",
            "Are you sure you want to solve all conflicts using the 'theirs' version?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ret == QMessageBox.Yes:
            pass

    def solveFeature(self):
        feature = {"properties": {}, "type": "Feature"}
        for row in range(self.tableAttributes.rowCount() - 1):
            attrib = self.tableAttributes.item(row, 3).text()
            finalItem = self.tableAttributes.item(row, 4)
            if finalItem.hasValue:
                feature["properties"][attrib] = finalItem.value
            else:
                self.bar.pushMessage(
                    "", "There are still conflicts in the current feature", Qgis.Warning
                )
                return
        geomItem = self.tableAttributes.item(self.tableAttributes.rowCount() - 1, 4)
        if geomItem.hasValue:
            feature["geometry"] = geomItem.value
        else:
            self.bar.pushMessage(
                "", "There are still conflicts in the current feature", Qgis.Warning
            )
            return
        feature[
            "id"
        ] = f"{self.lastSelectedItem.path}:feature:{self.lastSelectedItem.fid}"
        self.resolvedFeatures[feature["id"]] = feature
        self.updateAfterSolvingCurrentItem()

    def updateAfterSolvingCurrentItem(self):
        parent = self.lastSelectedItem.parent()
        parent.removeChild(self.lastSelectedItem)
        if not parent.childCount():
            idx = self.treeConflicts.indexOfTopLevelItem(parent)
            self.treeConflicts.takeTopLevelItem(idx)
            if not self.treeConflicts.topLevelItemCount():
                QMessageBox.warning(
                    self,
                    "Solve conflicts",
                    "All conflicts are solved. The merge operation will now be closed",
                    QMessageBox.Ok,
                    QMessageBox.Ok,
                )
                self.okToMerge = True
                self.close()
                return

        self.treeConflicts.setCurrentItem(self.treeConflicts.topLevelItem(0))
        self.updateFromCurrentSelectedItem()

    def solveOurs(self):
        conflict = self.lastSelectedItem.conflict
        feature = dict(conflict["ours"])
        feature[
            "id"
        ] = f"{self.lastSelectedItem.path}:feature:{self.lastSelectedItem.fid}"
        self.resolvedFeatures[feature["id"]] = feature
        self.updateAfterSolvingCurrentItem()

    def solveTheirs(self):
        conflict = self.lastSelectedItem.conflict
        feature = dict(conflict["theirs"])
        feature[
            "id"
        ] = f"{self.lastSelectedItem.path}:feature:{self.lastSelectedItem.fid}"
        self.resolvedFeatures[feature["id"]] = feature
        self.updateAfterSolvingCurrentItem()

    def solveWithDeleted(self):
        fid = f"{self.lastSelectedItem.path}:feature:{self.lastSelectedItem.fid}"
        self.resolvedFeatures[fid] = None
        self.updateAfterSolvingCurrentItem()

    def solveWithModified(self):
        conflict = self.lastSelectedItem.conflict
        feature = conflict["ours"] or conflict["theirs"]
        feature = dict(feature)
        feature[
            "id"
        ] = f"{self.lastSelectedItem.path}:feature:{self.lastSelectedItem.fid}"
        self.resolvedFeatures[feature["id"]] = feature
        self.updateAfterSolvingCurrentItem()

    def solveWithAncestor(self):
        conflict = self.lastSelectedItem.conflict
        feature = dict(conflict["ancestor"])
        feature[
            "id"
        ] = f"{self.lastSelectedItem.path}:feature:{self.lastSelectedItem.fid}"
        self.resolvedFeatures[feature["id"]] = feature
        self.updateAfterSolvingCurrentItem()

    def showSolveDeleted(self):
        self.stackedWidget.setCurrentWidget(self.pageSolveWithDeleted)

    def showFeatureAttributes(self):
        conflict = self.lastSelectedItem.conflict
        self.stackedWidget.setCurrentWidget(self.pageSolveNormal)
        attribs = list(conflict["ancestor"]["properties"].keys())
        attribs.append("geometry")
        self.tableAttributes.setRowCount(len(attribs))

        for idx, name in enumerate(attribs):
            font = QFont()
            font.setBold(True)
            font.setWeight(75)
            item = QTableWidgetItem(name)
            item.setFont(font)
            self.tableAttributes.setItem(idx, 3, item)

            versions = ["ancestor", "ours", "theirs"]
            values = []
            for v in versions:
                feature = conflict[v]
                if name == "geometry":
                    value = feature["geometry"]
                else:
                    value = feature["properties"][name]
                values.append(value)

            ok = (
                values[0] == values[1]
                or values[1] == values[2]
                or values[0] == values[2]
            )

            for i, v in enumerate(values):
                self.tableAttributes.setItem(idx, i, ValueItem(v, not ok))

            finalItem = FinalValueItem()
            if ok:
                finalItem.setValue(values[1] if values[0] == values[2] else values[2])
            self.tableAttributes.setItem(idx, 4, finalItem)

        self.tableAttributes.horizontalHeader().setMinimumSectionSize(100)
        self.tableAttributes.horizontalHeader().setStretchLastSection(True)
        self.tableAttributes.resizeColumnsToContents()
        header = self.tableAttributes.horizontalHeader()
        for column in range(header.count()):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            width = header.sectionSize(column)
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            header.resizeSection(column, min(150, width))

    def closeEvent(self, evnt):
        if not self.okToMerge:
            ret = QMessageBox.warning(
                self,
                "Conflict resolution",
                "Do you really want to exit without resolving conflicts?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ret == QMessageBox.No:
                evnt.ignore()
            else:
                self.resolvedFeatures = None


class ValueItem(QTableWidgetItem):
    def __init__(self, value, conflicted):
        QTableWidgetItem.__init__(self)
        self.value = value

        if conflicted:
            self.setBackground(Qt.yellow)
        else:
            self.setBackground(Qt.white)

        if isinstance(value, dict):
            s = value["type"]
        else:
            s = str(value)

        self.setText(s)
        self.setFlags(Qt.ItemIsEnabled)


class FinalValueItem(QTableWidgetItem):
    def __init__(self):
        QTableWidgetItem.__init__(self)
        self.hasValue = False
        self.value = None

        self.setText("")
        self.setBackground(Qt.yellow)
        # self.setFlags(Qt.ItemIsEnabled)

    def setValue(self, value):
        self.value = value
        self.hasValue = True

        if isinstance(value, dict):
            s = value["type"]
        else:
            s = str(value)
        self.setText(s)
        self.setBackground(Qt.white)


class ConflictItem(QTreeWidgetItem):
    def __init__(self, path, fid, conflict):
        QTreeWidgetItem.__init__(self)
        self.setText(0, fid)
        self.setIcon(0, featureIcon)
        self.setSizeHint(0, QSize(self.sizeHint(0).width(), 25))
        self.conflict = conflict
        self.fid = fid
        self.path = path
